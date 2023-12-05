# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for large portions of L{twisted.mail}.
"""

import email.message
import email.parser
import errno
import glob
import io
import os
import pickle
import shutil
import signal
import sys
import tempfile
import textwrap
import time
from hashlib import md5
from unittest import skipIf

from zope.interface import Interface, implementer
from zope.interface.verify import verifyClass

import twisted.cred.checkers
import twisted.cred.credentials
import twisted.cred.portal
import twisted.mail.alias
import twisted.mail.mail
import twisted.mail.maildir
import twisted.mail.protocols
import twisted.mail.relay
import twisted.mail.relaymanager
from twisted import cred, mail
from twisted.internet import address, defer, interfaces, protocol, reactor, task
from twisted.internet.defer import Deferred
from twisted.internet.error import (
    CannotListenError,
    DNSLookupError,
    ProcessDone,
    ProcessTerminated,
)
from twisted.mail import pop3, smtp
from twisted.mail.relaymanager import _AttemptManager
from twisted.names import dns
from twisted.names.dns import Record_CNAME, Record_MX, RRHeader
from twisted.names.error import DNSNameError
from twisted.python import failure, log
from twisted.python.filepath import FilePath
from twisted.python.runtime import platformType
from twisted.test.proto_helpers import (
    LineSendingProtocol,
    MemoryReactorClock,
    StringTransport,
)
from twisted.trial.unittest import TestCase


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class DomainWithDefaultsTests(TestCase):
    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testMethods(self):
        d = {x: x + 10 for x in range(10)}
        d = mail.mail.DomainWithDefaultDict(d, "Default")

        self.assertEqual(len(d), 10)
        self.assertEqual(list(iter(d)), list(range(10)))
        self.assertEqual(list(d.iterkeys()), list(iter(d)))

        items = list(d.iteritems())
        items.sort()
        self.assertEqual(items, [(x, x + 10) for x in range(10)])

        values = list(d.itervalues())
        values.sort()
        self.assertEqual(values, list(range(10, 20)))

        items = d.items()
        items.sort()
        self.assertEqual(items, [(x, x + 10) for x in range(10)])

        values = d.values()
        values.sort()
        self.assertEqual(values, list(range(10, 20)))

        for x in range(10):
            self.assertEqual(d[x], x + 10)
            self.assertEqual(d.get(x), x + 10)
            self.assertTrue(x in d)

        del d[2], d[4], d[6]

        self.assertEqual(len(d), 7)
        self.assertEqual(d[2], "Default")
        self.assertEqual(d[4], "Default")
        self.assertEqual(d[6], "Default")

        d.update({"a": None, "b": (), "c": "*"})
        self.assertEqual(len(d), 10)
        self.assertEqual(d["a"], None)
        self.assertEqual(d["b"], ())
        self.assertEqual(d["c"], "*")

        d.clear()
        self.assertEqual(len(d), 0)

        self.assertEqual(d.setdefault("key", "value"), "value")
        self.assertEqual(d["key"], "value")

        self.assertEqual(d.popitem(), ("key", "value"))
        self.assertEqual(len(d), 0)

        dcopy = d.copy()
        self.assertEqual(d.domains, dcopy.domains)
        self.assertEqual(d.default, dcopy.default)

    def _stringificationTest(self, stringifier):
        """
        Assert that the class name of a L{mail.mail.DomainWithDefaultDict}
        instance and the string-formatted underlying domain dictionary both
        appear in the string produced by the given string-returning function.

        @type stringifier: one-argument callable
        @param stringifier: either C{str} or C{repr}, to be used to get a
            string to make assertions against.
        """
        domain = mail.mail.DomainWithDefaultDict({}, "Default")
        self.assertIn(domain.__class__.__name__, stringifier(domain))
        domain["key"] = "value"
        self.assertIn(str({"key": "value"}), stringifier(domain))

    def test_str(self):
        """
        L{DomainWithDefaultDict.__str__} should return a string including
        the class name and the domain mapping held by the instance.
        """
        self._stringificationTest(str)

    def test_repr(self):
        """
        L{DomainWithDefaultDict.__repr__} should return a string including
        the class name and the domain mapping held by the instance.
        """
        self._stringificationTest(repr)

    def test_has_keyDeprecation(self):
        """
        has_key is now deprecated.
        """
        sut = mail.mail.DomainWithDefaultDict({}, "Default")

        sut.has_key("anything")

        message = (
            "twisted.mail.mail.DomainWithDefaultDict.has_key was deprecated "
            "in Twisted 16.3.0. Use the `in` keyword instead."
        )
        warnings = self.flushWarnings([self.test_has_keyDeprecation])
        self.assertEqual(1, len(warnings))
        self.assertEqual(DeprecationWarning, warnings[0]["category"])
        self.assertEqual(message, warnings[0]["message"])


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class BounceTests(TestCase):
    def setUp(self):
        self.domain = mail.mail.BounceDomain()

    def testExists(self):
        self.assertRaises(smtp.AddressError, self.domain.exists, "any user")

    def testRelay(self):
        self.assertEqual(self.domain.willRelay("random q emailer", "protocol"), False)

    def testAddUser(self):
        self.domain.addUser("bob", "password")
        self.assertRaises(smtp.SMTPBadRcpt, self.domain.exists, "bob")


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class BounceWithSMTPServerTests(TestCase):
    """
    Tests for L{twisted.mail.mail.BounceDomain} with
    L{twisted.mail.smtp.SMTPServer}.
    """

    def test_rejected(self):
        """
        Incoming emails to a SMTP server with L{twisted.mail.mail.BounceDomain}
        are rejected.
        """
        service = mail.mail.MailService()
        domain = mail.mail.BounceDomain()
        service.addDomain(b"foo.com", domain)

        factory = mail.protocols.SMTPFactory(service)
        protocol = factory.buildProtocol(None)

        deliverer = mail.protocols.SMTPDomainDelivery(service, None, None)
        protocol.delivery = deliverer

        transport = StringTransport()
        protocol.makeConnection(transport)

        protocol.lineReceived(b"HELO baz.net")
        protocol.lineReceived(b"MAIL FROM:<a@baz.net>")
        protocol.lineReceived(b"RCPT TO:<any@foo.com>")
        protocol.lineReceived(b"QUIT")

        self.assertTrue(transport.disconnecting)
        protocol.connectionLost(None)

        self.assertEqual(
            transport.value().strip().split(b"\r\n")[-2],
            b"550 Cannot receive for specified address",
        )


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class FileMessageTests(TestCase):
    def setUp(self):
        self.name = self.mktemp()
        self.final = self.mktemp()
        self.f = open(self.name, "wb")
        self.addCleanup(self.f.close)
        self.fp = mail.mail.FileMessage(self.f, self.name, self.final)

    def testFinalName(self):
        return self.fp.eomReceived().addCallback(self._cbFinalName)

    def _cbFinalName(self, result):
        self.assertEqual(result, self.final)
        self.assertTrue(self.f.closed)
        self.assertFalse(os.path.exists(self.name))

    def testContents(self):
        contents = b"first line\nsecond line\nthird line\n"
        for line in contents.splitlines():
            self.fp.lineReceived(line)
        self.fp.eomReceived()
        with open(self.final, "rb") as f:
            self.assertEqual(f.read(), contents)

    def testInterrupted(self):
        contents = b"first line\nsecond line\n"
        for line in contents.splitlines():
            self.fp.lineReceived(line)
        self.fp.connectionLost()
        self.assertFalse(os.path.exists(self.name))
        self.assertFalse(os.path.exists(self.final))


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class MaildirMessageTests(TestCase):
    """
    Tests for the file creating by the L{mail.maildir.MaildirMessage}.
    """

    def setUp(self):
        """
        Create and open a temporary file.
        """
        self.name = self.mktemp()
        self.final = self.mktemp()
        self.address = b"user@example.com"
        self.f = open(self.name, "wb")
        self.addCleanup(self.f.close)
        self.fp = mail.maildir.MaildirMessage(
            self.address, self.f, self.name, self.final
        )

    def _finalName(self):
        """
        Search for the final file path.

        @rtype: L{str}
        @return: Final file path.
        """
        return glob.glob(f"{self.final},S=[0-9]*")[0]

    def test_finalName(self):
        """
        Send the EOM to the message and check that the final file name contains
        the correct file size and the temporary file has been closed and removed.
        """
        final = self.successResultOf(self.fp.eomReceived())
        self.assertEqual(final, f"{self.final},S={os.path.getsize(final)}")
        self.assertTrue(self.f.closed)
        self.assertFalse(os.path.exists(self.name))

    def test_contents(self):
        """
        Send a message contents and the EOM to the message and check that the
        final file contains the correct header and the message contents.
        """
        contents = b"first line\nsecond line\nthird line\n"
        for line in contents.splitlines():
            self.fp.lineReceived(line)
        final = self.successResultOf(self.fp.eomReceived())
        with open(final, "rb") as f:
            self.assertEqual(
                f.read(), b"Delivered-To: %s\n%s" % (self.address, contents)
            )

    def test_interrupted(self):
        """
        Check that the interrupted message transfer removes the temporary file
        and a doesn't create a final file.
        """
        contents = b"first line\nsecond line\n"
        for line in contents.splitlines():
            self.fp.lineReceived(line)
        self.fp.connectionLost()
        self.assertFalse(os.path.exists(self.name))
        self.assertRaises(IndexError, self._finalName)


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class MailServiceTests(TestCase):
    def setUp(self):
        self.service = mail.mail.MailService()

    def testFactories(self):
        f = self.service.getPOP3Factory()
        self.assertTrue(isinstance(f, protocol.ServerFactory))
        self.assertTrue(f.buildProtocol(("127.0.0.1", 12345)), pop3.POP3)

        f = self.service.getSMTPFactory()
        self.assertTrue(isinstance(f, protocol.ServerFactory))
        self.assertTrue(f.buildProtocol(("127.0.0.1", 12345)), smtp.SMTP)

        f = self.service.getESMTPFactory()
        self.assertTrue(isinstance(f, protocol.ServerFactory))
        self.assertTrue(f.buildProtocol(("127.0.0.1", 12345)), smtp.ESMTP)

    def testPortals(self):
        o1 = object()
        o2 = object()
        self.service.portals["domain"] = o1
        self.service.portals[""] = o2

        self.assertTrue(self.service.lookupPortal("domain") is o1)
        self.assertTrue(self.service.defaultPortal() is o2)


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class StringListMailboxTests(TestCase):
    """
    Tests for L{StringListMailbox}, an in-memory only implementation of
    L{pop3.IMailbox}.
    """

    def test_listOneMessage(self):
        """
        L{StringListMailbox.listMessages} returns the length of the message at
        the offset into the mailbox passed to it.
        """
        mailbox = mail.maildir.StringListMailbox(["abc", "ab", "a"])
        self.assertEqual(mailbox.listMessages(0), 3)
        self.assertEqual(mailbox.listMessages(1), 2)
        self.assertEqual(mailbox.listMessages(2), 1)

    def test_listAllMessages(self):
        """
        L{StringListMailbox.listMessages} returns a list of the lengths of all
        messages if not passed an index.
        """
        mailbox = mail.maildir.StringListMailbox(["a", "abc", "ab"])
        self.assertEqual(mailbox.listMessages(), [1, 3, 2])

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_getMessage(self):
        """
        L{StringListMailbox.getMessage} returns a file-like object from which
        the contents of the message at the given offset into the mailbox can be
        read.
        """
        mailbox = mail.maildir.StringListMailbox(["foo", "real contents"])
        self.assertEqual(mailbox.getMessage(1).read(), "real contents")

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_getUidl(self):
        """
        L{StringListMailbox.getUidl} returns a unique identifier for the
        message at the given offset into the mailbox.
        """
        mailbox = mail.maildir.StringListMailbox(["foo", "bar"])
        self.assertNotEqual(mailbox.getUidl(0), mailbox.getUidl(1))

    def test_deleteMessage(self):
        """
        L{StringListMailbox.deleteMessage} marks a message for deletion causing
        further requests for its length to return 0.
        """
        mailbox = mail.maildir.StringListMailbox(["foo"])
        mailbox.deleteMessage(0)
        self.assertEqual(mailbox.listMessages(0), 0)
        self.assertEqual(mailbox.listMessages(), [0])

    def test_undeleteMessages(self):
        """
        L{StringListMailbox.undeleteMessages} causes any messages marked for
        deletion to be returned to their original state.
        """
        mailbox = mail.maildir.StringListMailbox(["foo"])
        mailbox.deleteMessage(0)
        mailbox.undeleteMessages()
        self.assertEqual(mailbox.listMessages(0), 3)
        self.assertEqual(mailbox.listMessages(), [3])

    def test_sync(self):
        """
        L{StringListMailbox.sync} causes any messages as marked for deletion to
        be permanently deleted.
        """
        mailbox = mail.maildir.StringListMailbox(["foo"])
        mailbox.deleteMessage(0)
        mailbox.sync()
        mailbox.undeleteMessages()
        self.assertEqual(mailbox.listMessages(0), 0)
        self.assertEqual(mailbox.listMessages(), [0])


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class FailingMaildirMailboxAppendMessageTask(
    mail.maildir._MaildirMailboxAppendMessageTask
):
    _openstate = True
    _writestate = True
    _renamestate = True

    def osopen(self, fn, attr, mode):
        if self._openstate:
            return os.open(fn, attr, mode)
        else:
            raise OSError(errno.EPERM, "Faked Permission Problem")

    def oswrite(self, fh, data):
        if self._writestate:
            return os.write(fh, data)
        else:
            raise OSError(errno.ENOSPC, "Faked Space problem")

    def osrename(self, oldname, newname):
        if self._renamestate:
            return os.rename(oldname, newname)
        else:
            raise OSError(errno.EPERM, "Faked Permission Problem")


class _AppendTestMixin:
    """
    Mixin for L{MaildirMailbox.appendMessage} test cases which defines a helper
    for serially appending multiple messages to a mailbox.
    """

    def _appendMessages(self, mbox, messages):
        """
        Deliver the given messages one at a time.  Delivery is serialized to
        guarantee a predictable order in the mailbox (overlapped message deliver
        makes no guarantees about which message which appear first).
        """
        results = []

        def append():
            for m in messages:
                d = mbox.appendMessage(m)
                d.addCallback(results.append)
                yield d

        d = task.cooperate(append()).whenDone()
        d.addCallback(lambda ignored: results)
        return d


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class MaildirAppendStringTests(TestCase, _AppendTestMixin):
    """
    Tests for L{MaildirMailbox.appendMessage} when invoked with a C{str}.
    """

    def setUp(self):
        self.d = self.mktemp()
        mail.maildir.initializeMaildir(self.d)

    def _append(self, ignored, mbox):
        d = mbox.appendMessage("TEST")
        return self.assertFailure(d, Exception)

    def _setState(self, ignored, mbox, rename=None, write=None, open=None):
        """
        Change the behavior of future C{rename}, C{write}, or C{open} calls made
        by the mailbox C{mbox}.

        @param rename: If not L{None}, a new value for the C{_renamestate}
            attribute of the mailbox's append factory.  The original value will
            be restored at the end of the test.

        @param write: Like C{rename}, but for the C{_writestate} attribute.

        @param open: Like C{rename}, but for the C{_openstate} attribute.
        """
        if rename is not None:
            self.addCleanup(
                setattr,
                mbox.AppendFactory,
                "_renamestate",
                mbox.AppendFactory._renamestate,
            )
            mbox.AppendFactory._renamestate = rename
        if write is not None:
            self.addCleanup(
                setattr,
                mbox.AppendFactory,
                "_writestate",
                mbox.AppendFactory._writestate,
            )
            mbox.AppendFactory._writestate = write
        if open is not None:
            self.addCleanup(
                setattr, mbox.AppendFactory, "_openstate", mbox.AppendFactory._openstate
            )
            mbox.AppendFactory._openstate = open

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_append(self):
        """
        L{MaildirMailbox.appendMessage} returns a L{Deferred} which fires when
        the message has been added to the end of the mailbox.
        """
        mbox = mail.maildir.MaildirMailbox(self.d)
        mbox.AppendFactory = FailingMaildirMailboxAppendMessageTask

        d = self._appendMessages(mbox, ["X" * i for i in range(1, 11)])
        d.addCallback(self.assertEqual, [None] * 10)
        d.addCallback(self._cbTestAppend, mbox)
        return d

    def _cbTestAppend(self, ignored, mbox):
        """
        Check that the mailbox has the expected number (ten) of messages in it,
        and that each has the expected contents, and that they are in the same
        order as that in which they were appended.
        """
        self.assertEqual(len(mbox.listMessages()), 10)
        self.assertEqual(
            [len(mbox.getMessage(i).read()) for i in range(10)], list(range(1, 11))
        )
        # test in the right order: last to first error location.
        self._setState(None, mbox, rename=False)
        d = self._append(None, mbox)
        d.addCallback(self._setState, mbox, rename=True, write=False)
        d.addCallback(self._append, mbox)
        d.addCallback(self._setState, mbox, write=True, open=False)
        d.addCallback(self._append, mbox)
        d.addCallback(self._setState, mbox, open=True)
        return d


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class MaildirAppendFileTests(TestCase, _AppendTestMixin):
    """
    Tests for L{MaildirMailbox.appendMessage} when invoked with a C{str}.
    """

    def setUp(self):
        self.d = self.mktemp()
        mail.maildir.initializeMaildir(self.d)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_append(self):
        """
        L{MaildirMailbox.appendMessage} returns a L{Deferred} which fires when
        the message has been added to the end of the mailbox.
        """
        mbox = mail.maildir.MaildirMailbox(self.d)
        messages = []
        for i in range(1, 11):
            temp = tempfile.TemporaryFile()
            temp.write("X" * i)
            temp.seek(0, 0)
            messages.append(temp)
            self.addCleanup(temp.close)

        d = self._appendMessages(mbox, messages)
        d.addCallback(self._cbTestAppend, mbox)
        return d

    def _cbTestAppend(self, result, mbox):
        """
        Check that the mailbox has the expected number (ten) of messages in it,
        and that each has the expected contents, and that they are in the same
        order as that in which they were appended.
        """
        self.assertEqual(len(mbox.listMessages()), 10)
        self.assertEqual(
            [len(mbox.getMessage(i).read()) for i in range(10)], list(range(1, 11))
        )


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class MaildirTests(TestCase):
    def setUp(self):
        self.d = self.mktemp()
        mail.maildir.initializeMaildir(self.d)

    def tearDown(self):
        shutil.rmtree(self.d)

    def testInitializer(self):
        d = self.d
        trash = os.path.join(d, ".Trash")

        self.assertTrue(os.path.exists(d) and os.path.isdir(d))
        self.assertTrue(os.path.exists(os.path.join(d, "new")))
        self.assertTrue(os.path.exists(os.path.join(d, "cur")))
        self.assertTrue(os.path.exists(os.path.join(d, "tmp")))
        self.assertTrue(os.path.isdir(os.path.join(d, "new")))
        self.assertTrue(os.path.isdir(os.path.join(d, "cur")))
        self.assertTrue(os.path.isdir(os.path.join(d, "tmp")))

        self.assertTrue(os.path.exists(os.path.join(trash, "new")))
        self.assertTrue(os.path.exists(os.path.join(trash, "cur")))
        self.assertTrue(os.path.exists(os.path.join(trash, "tmp")))
        self.assertTrue(os.path.isdir(os.path.join(trash, "new")))
        self.assertTrue(os.path.isdir(os.path.join(trash, "cur")))
        self.assertTrue(os.path.isdir(os.path.join(trash, "tmp")))

    def test_nameGenerator(self):
        """
        Each call to L{_MaildirNameGenerator.generate} returns a unique
        string suitable for use as the basename of a new message file.  The
        names are ordered such that those generated earlier sort less than
        those generated later.
        """
        clock = task.Clock()
        clock.advance(0.05)
        generator = mail.maildir._MaildirNameGenerator(clock)

        firstName = generator.generate()
        clock.advance(0.05)
        secondName = generator.generate()

        self.assertTrue(firstName < secondName)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_mailbox(self):
        """
        Exercise the methods of L{IMailbox} as implemented by
        L{MaildirMailbox}.
        """
        j = os.path.join
        n = mail.maildir._generateMaildirName
        msgs = [j(b, n()) for b in ("cur", "new") for x in range(5)]

        # Toss a few files into the mailbox
        i = 1
        for f in msgs:
            with open(j(self.d, f), "w") as fObj:
                fObj.write("x" * i)
            i = i + 1

        mb = mail.maildir.MaildirMailbox(self.d)
        self.assertEqual(mb.listMessages(), list(range(1, 11)))
        self.assertEqual(mb.listMessages(1), 2)
        self.assertEqual(mb.listMessages(5), 6)

        self.assertEqual(mb.getMessage(6).read(), "x" * 7)
        self.assertEqual(mb.getMessage(1).read(), "x" * 2)

        d = {}
        for i in range(10):
            u = mb.getUidl(i)
            self.assertFalse(u in d)
            d[u] = None

        p, f = os.path.split(msgs[5])

        mb.deleteMessage(5)
        self.assertEqual(mb.listMessages(5), 0)
        self.assertTrue(os.path.exists(j(self.d, ".Trash", "cur", f)))
        self.assertFalse(os.path.exists(j(self.d, msgs[5])))

        mb.undeleteMessages()
        self.assertEqual(mb.listMessages(5), 6)
        self.assertFalse(os.path.exists(j(self.d, ".Trash", "cur", f)))
        self.assertTrue(os.path.exists(j(self.d, msgs[5])))


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class AbstractMaildirDomainTests(TestCase):
    """
    Tests for L{twisted.mail.maildir.AbstractMaildirDomain}.
    """

    def test_interface(self):
        """
        L{maildir.AbstractMaildirDomain} implements L{mail.IAliasableDomain}.
        """
        verifyClass(mail.mail.IAliasableDomain, mail.maildir.AbstractMaildirDomain)


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class MaildirDirdbmDomainTests(TestCase):
    """
    Tests for L{MaildirDirdbmDomain}.
    """

    def setUp(self):
        """
        Create a temporary L{MaildirDirdbmDomain} and parent
        L{MailService} before running each test.
        """
        self.P = self.mktemp()
        self.S = mail.mail.MailService()
        self.D = mail.maildir.MaildirDirdbmDomain(self.S, self.P)

    def tearDown(self):
        """
        Remove the temporary C{maildir} directory when the test has
        finished.
        """
        shutil.rmtree(self.P)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_addUser(self):
        """
        L{MaildirDirdbmDomain.addUser} accepts a user and password
        argument. It stores those in a C{dbm} dictionary
        attribute and creates a directory for each user.
        """
        toAdd = (("user1", "pwd1"), ("user2", "pwd2"), ("user3", "pwd3"))
        for (u, p) in toAdd:
            self.D.addUser(u, p)

        for (u, p) in toAdd:
            self.assertTrue(u in self.D.dbm)
            self.assertEqual(self.D.dbm[u], p)
            self.assertTrue(os.path.exists(os.path.join(self.P, u)))

    def test_credentials(self):
        """
        L{MaildirDirdbmDomain.getCredentialsCheckers} initializes and
        returns one L{ICredentialsChecker} checker by default.
        """
        creds = self.D.getCredentialsCheckers()

        self.assertEqual(len(creds), 1)
        self.assertTrue(cred.checkers.ICredentialsChecker.providedBy(creds[0]))
        self.assertTrue(
            cred.credentials.IUsernamePassword in creds[0].credentialInterfaces
        )

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_requestAvatar(self):
        """
        L{MaildirDirdbmDomain.requestAvatar} raises L{NotImplementedError}
        unless it is supplied with an L{pop3.IMailbox} interface.
        When called with an L{pop3.IMailbox}, it returns a 3-tuple
        containing L{pop3.IMailbox}, an implementation of that interface
        and a NOOP callable.
        """

        class ISomething(Interface):
            pass

        self.D.addUser("user", "password")
        self.assertRaises(
            NotImplementedError, self.D.requestAvatar, "user", None, ISomething
        )

        t = self.D.requestAvatar("user", None, pop3.IMailbox)
        self.assertEqual(len(t), 3)
        self.assertTrue(t[0] is pop3.IMailbox)
        self.assertTrue(pop3.IMailbox.providedBy(t[1]))

        t[2]()

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_requestAvatarId(self):
        """
        L{DirdbmDatabase.requestAvatarId} raises L{UnauthorizedLogin} if
        supplied with invalid user credentials.
        When called with valid credentials, L{requestAvatarId} returns
        the username associated with the supplied credentials.
        """
        self.D.addUser("user", "password")
        database = self.D.getCredentialsCheckers()[0]

        creds = cred.credentials.UsernamePassword("user", "wrong password")
        self.assertRaises(cred.error.UnauthorizedLogin, database.requestAvatarId, creds)

        creds = cred.credentials.UsernamePassword("user", "password")
        self.assertEqual(database.requestAvatarId(creds), "user")

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_userDirectory(self):
        """
        L{MaildirDirdbmDomain.userDirectory} is supplied with a user name
        and returns the path to that user's maildir subdirectory.
        Calling L{MaildirDirdbmDomain.userDirectory} with a
        non-existent user returns the 'postmaster' directory if there
        is a postmaster or returns L{None} if there is no postmaster.
        """
        self.D.addUser("user", "password")
        self.assertEqual(
            self.D.userDirectory("user"), os.path.join(self.D.root, "user")
        )

        self.D.postmaster = False
        self.assertIdentical(self.D.userDirectory("nouser"), None)

        self.D.postmaster = True
        self.assertEqual(
            self.D.userDirectory("nouser"), os.path.join(self.D.root, "postmaster")
        )


@implementer(mail.mail.IAliasableDomain)
class StubAliasableDomain:
    """
    Minimal testable implementation of IAliasableDomain.
    """

    def exists(self, user, memo=None):
        """
        No test coverage for invocations of this method on domain objects,
        so we just won't implement it.
        """
        raise NotImplementedError()

    def addUser(self, user, password):
        """
        No test coverage for invocations of this method on domain objects,
        so we just won't implement it.
        """
        raise NotImplementedError()

    def getCredentialsCheckers(self):
        """
        This needs to succeed in order for other tests to complete
        successfully, but we don't actually assert anything about its
        behavior.  Return an empty list.  Sometime later we should return
        something else and assert that a portal got set up properly.
        """
        return []

    def setAliasGroup(self, aliases):
        """
        Just record the value so the test can check it later.
        """
        self.aliasGroup = aliases


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class ServiceDomainTests(TestCase):
    def setUp(self):
        self.S = mail.mail.MailService()
        self.D = mail.protocols.DomainDeliveryBase(self.S, None)
        self.D.service = self.S
        self.D.protocolName = "TEST"
        self.D.host = "hostname"

        self.tmpdir = self.mktemp()
        domain = mail.maildir.MaildirDirdbmDomain(self.S, self.tmpdir)
        domain.addUser(b"user", b"password")
        self.S.addDomain("test.domain", domain)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def testAddAliasableDomain(self):
        """
        Test that adding an IAliasableDomain to a mail service properly sets
        up alias group references and such.
        """
        aliases = object()
        domain = StubAliasableDomain()
        self.S.aliases = aliases
        self.S.addDomain("example.com", domain)
        self.assertIdentical(domain.aliasGroup, aliases)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testReceivedHeader(self):
        hdr = self.D.receivedHeader(
            ("remotehost", "123.232.101.234"),
            smtp.Address("<someguy@someplace>"),
            ["user@host.name"],
        )
        fp = io.BytesIO(hdr)
        emailParser = email.parser.Parser()
        m = emailParser.parse(fp)
        self.assertEqual(len(m.items()), 1)
        self.assertIn("Received", m)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testValidateTo(self):
        user = smtp.User("user@test.domain", "helo", None, "wherever@whatever")
        return defer.maybeDeferred(self.D.validateTo, user).addCallback(
            self._cbValidateTo
        )

    def _cbValidateTo(self, result):
        self.assertTrue(callable(result))

    def testValidateToBadUsername(self):
        user = smtp.User("resu@test.domain", "helo", None, "wherever@whatever")
        return self.assertFailure(
            defer.maybeDeferred(self.D.validateTo, user), smtp.SMTPBadRcpt
        )

    def testValidateToBadDomain(self):
        user = smtp.User("user@domain.test", "helo", None, "wherever@whatever")
        return self.assertFailure(
            defer.maybeDeferred(self.D.validateTo, user), smtp.SMTPBadRcpt
        )

    def testValidateFrom(self):
        helo = ("hostname", "127.0.0.1")
        origin = smtp.Address("<user@hostname>")
        self.assertTrue(self.D.validateFrom(helo, origin) is origin)

        helo = ("hostname", "1.2.3.4")
        origin = smtp.Address("<user@hostname>")
        self.assertTrue(self.D.validateFrom(helo, origin) is origin)

        helo = ("hostname", "1.2.3.4")
        origin = smtp.Address("<>")
        self.assertTrue(self.D.validateFrom(helo, origin) is origin)

        self.assertRaises(smtp.SMTPBadSender, self.D.validateFrom, None, origin)


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class VirtualPOP3Tests(TestCase):
    def setUp(self):
        self.tmpdir = self.mktemp()
        self.S = mail.mail.MailService()
        self.D = mail.maildir.MaildirDirdbmDomain(self.S, self.tmpdir)
        self.D.addUser(b"user", b"password")
        self.S.addDomain("test.domain", self.D)

        portal = cred.portal.Portal(self.D)
        map(portal.registerChecker, self.D.getCredentialsCheckers())
        self.S.portals[""] = self.S.portals["test.domain"] = portal

        self.P = mail.protocols.VirtualPOP3()
        self.P.service = self.S
        self.P.magic = "<unit test magic>"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testAuthenticateAPOP(self):
        resp = md5(self.P.magic + "password").hexdigest()
        return self.P.authenticateUserAPOP("user", resp).addCallback(
            self._cbAuthenticateAPOP
        )

    def _cbAuthenticateAPOP(self, result):
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], pop3.IMailbox)
        self.assertTrue(pop3.IMailbox.providedBy(result[1]))
        result[2]()

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testAuthenticateIncorrectUserAPOP(self):
        resp = md5(self.P.magic + "password").hexdigest()
        return self.assertFailure(
            self.P.authenticateUserAPOP("resu", resp), cred.error.UnauthorizedLogin
        )

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testAuthenticateIncorrectResponseAPOP(self):
        resp = md5("wrong digest").hexdigest()
        return self.assertFailure(
            self.P.authenticateUserAPOP("user", resp), cred.error.UnauthorizedLogin
        )

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testAuthenticatePASS(self):
        return self.P.authenticateUserPASS("user", "password").addCallback(
            self._cbAuthenticatePASS
        )

    def _cbAuthenticatePASS(self, result):
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], pop3.IMailbox)
        self.assertTrue(pop3.IMailbox.providedBy(result[1]))
        result[2]()

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testAuthenticateBadUserPASS(self):
        return self.assertFailure(
            self.P.authenticateUserPASS("resu", "password"),
            cred.error.UnauthorizedLogin,
        )

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testAuthenticateBadPasswordPASS(self):
        return self.assertFailure(
            self.P.authenticateUserPASS("user", "wrong password"),
            cred.error.UnauthorizedLogin,
        )


class empty(smtp.User):
    def __init__(self):
        pass


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class RelayTests(TestCase):
    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testExists(self):
        service = mail.mail.MailService()
        domain = mail.relay.DomainQueuer(service)

        doRelay = [
            address.UNIXAddress("/var/run/mail-relay"),
            address.IPv4Address("TCP", "127.0.0.1", 12345),
        ]

        dontRelay = [
            address.IPv4Address("TCP", "192.168.2.1", 62),
            address.IPv4Address("TCP", "1.2.3.4", 1943),
        ]

        for peer in doRelay:
            user = empty()
            user.orig = "user@host"
            user.dest = "tsoh@resu"
            user.protocol = empty()
            user.protocol.transport = empty()
            user.protocol.transport.getPeer = lambda: peer

            self.assertTrue(callable(domain.exists(user)))

        for peer in dontRelay:
            user = empty()
            user.orig = "some@place"
            user.protocol = empty()
            user.protocol.transport = empty()
            user.protocol.transport.getPeer = lambda: peer
            user.dest = "who@cares"

            self.assertRaises(smtp.SMTPBadRcpt, domain.exists, user)


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class RelayerTests(TestCase):
    def setUp(self):
        self.tmpdir = self.mktemp()
        os.mkdir(self.tmpdir)
        self.messageFiles = []
        for i in range(10):
            name = os.path.join(self.tmpdir, "body-%d" % (i,))
            with open(name + "-H", "wb") as f:
                pickle.dump(["from-%d" % (i,), "to-%d" % (i,)], f)

            f = open(name + "-D", "w")
            f.write(name)
            f.seek(0, 0)
            self.messageFiles.append(name)

        self.R = mail.relay.RelayerMixin()
        self.R.loadMessages(self.messageFiles)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def testMailFrom(self):
        for i in range(10):
            self.assertEqual(self.R.getMailFrom(), "from-%d" % (i,))
            self.R.sentMail(250, None, None, None, None)
        self.assertEqual(self.R.getMailFrom(), None)

    def testMailTo(self):
        for i in range(10):
            self.assertEqual(self.R.getMailTo(), ["to-%d" % (i,)])
            self.R.sentMail(250, None, None, None, None)
        self.assertEqual(self.R.getMailTo(), None)

    def testMailData(self):
        for i in range(10):
            name = os.path.join(self.tmpdir, "body-%d" % (i,))
            self.assertEqual(self.R.getMailData().read(), name)
            self.R.sentMail(250, None, None, None, None)
        self.assertEqual(self.R.getMailData(), None)


class Manager:
    def __init__(self):
        self.success = []
        self.failure = []
        self.done = []

    def notifySuccess(self, factory, message):
        self.success.append((factory, message))

    def notifyFailure(self, factory, message):
        self.failure.append((factory, message))

    def notifyDone(self, factory):
        self.done.append(factory)


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class ManagedRelayerTests(TestCase):
    def setUp(self):
        self.manager = Manager()
        self.messages = list(range(0, 20, 2))
        self.factory = object()
        self.relay = mail.relaymanager.ManagedRelayerMixin(self.manager)
        self.relay.messages = self.messages[:]
        self.relay.names = self.messages[:]
        self.relay.factory = self.factory

    def testSuccessfulSentMail(self):
        for i in self.messages:
            self.relay.sentMail(250, None, None, None, None)

        self.assertEqual(
            self.manager.success, [(self.factory, m) for m in self.messages]
        )

    def testFailedSentMail(self):
        for i in self.messages:
            self.relay.sentMail(550, None, None, None, None)

        self.assertEqual(
            self.manager.failure, [(self.factory, m) for m in self.messages]
        )

    def testConnectionLost(self):
        self.relay.connectionLost(failure.Failure(Exception()))
        self.assertEqual(self.manager.done, [self.factory])


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class DirectoryQueueTests(TestCase):
    def setUp(self):
        # This is almost a test case itself.
        self.tmpdir = self.mktemp()
        os.mkdir(self.tmpdir)
        self.queue = mail.relaymanager.Queue(self.tmpdir)
        self.queue.noisy = False
        for m in range(25):
            hdrF, msgF = self.queue.createNewMessage()
            with hdrF:
                pickle.dump(["header", m], hdrF)
            msgF.lineReceived(b"body: %d" % (m,))
            msgF.eomReceived()
        self.queue.readDirectory()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testWaiting(self):
        self.assertTrue(self.queue.hasWaiting())
        self.assertEqual(len(self.queue.getWaiting()), 25)

        waiting = self.queue.getWaiting()
        self.queue.setRelaying(waiting[0])
        self.assertEqual(len(self.queue.getWaiting()), 24)

        self.queue.setWaiting(waiting[0])
        self.assertEqual(len(self.queue.getWaiting()), 25)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testRelaying(self):
        for m in self.queue.getWaiting():
            self.queue.setRelaying(m)
            self.assertEqual(
                len(self.queue.getRelayed()), 25 - len(self.queue.getWaiting())
            )

        self.assertFalse(self.queue.hasWaiting())

        relayed = self.queue.getRelayed()
        self.queue.setWaiting(relayed[0])
        self.assertEqual(len(self.queue.getWaiting()), 1)
        self.assertEqual(len(self.queue.getRelayed()), 24)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testDone(self):
        msg = self.queue.getWaiting()[0]
        self.queue.setRelaying(msg)
        self.queue.done(msg)

        self.assertEqual(len(self.queue.getWaiting()), 24)
        self.assertEqual(len(self.queue.getRelayed()), 0)

        self.assertFalse(msg in self.queue.getWaiting())
        self.assertFalse(msg in self.queue.getRelayed())

    def testEnvelope(self):
        envelopes = []

        for msg in self.queue.getWaiting():
            envelopes.append(self.queue.getEnvelope(msg))

        envelopes.sort()
        for i in range(25):
            self.assertEqual(envelopes.pop(0), ["header", i])


from twisted.names import client, common, server


class TestAuthority(common.ResolverBase):
    def __init__(self):
        common.ResolverBase.__init__(self)
        self.addresses = {}

    def _lookup(self, name, cls, type, timeout=None):
        if name in self.addresses and type == dns.MX:
            results = []
            for a in self.addresses[name]:
                hdr = dns.RRHeader(name, dns.MX, dns.IN, 60, dns.Record_MX(0, a))
                results.append(hdr)
            return defer.succeed((results, [], []))
        return defer.fail(failure.Failure(dns.DomainError(name)))


def setUpDNS(self):
    self.auth = TestAuthority()
    factory = server.DNSServerFactory([self.auth])
    protocol = dns.DNSDatagramProtocol(factory)
    while 1:
        self.port = reactor.listenTCP(0, factory, interface="127.0.0.1")
        portNumber = self.port.getHost().port

        try:
            self.udpPort = reactor.listenUDP(
                portNumber, protocol, interface="127.0.0.1"
            )
        except CannotListenError:
            self.port.stopListening()
        else:
            break
    self.resolver = client.Resolver(servers=[("127.0.0.1", portNumber)])


def tearDownDNS(self):
    dl = []
    dl.append(defer.maybeDeferred(self.port.stopListening))
    dl.append(defer.maybeDeferred(self.udpPort.stopListening))
    try:
        self.resolver._parseCall.cancel()
    except BaseException:
        pass
    return defer.DeferredList(dl)


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class MXTests(TestCase):
    """
    Tests for L{mail.relaymanager.MXCalculator}.
    """

    def setUp(self):
        setUpDNS(self)
        self.clock = task.Clock()
        self.mx = mail.relaymanager.MXCalculator(self.resolver, self.clock)

    def tearDown(self):
        return tearDownDNS(self)

    def test_defaultClock(self):
        """
        L{MXCalculator}'s default clock is C{twisted.internet.reactor}.
        """
        self.assertIdentical(
            mail.relaymanager.MXCalculator(self.resolver).clock, reactor
        )

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testSimpleSuccess(self):
        self.auth.addresses["test.domain"] = ["the.email.test.domain"]
        return self.mx.getMX("test.domain").addCallback(self._cbSimpleSuccess)

    def _cbSimpleSuccess(self, mx):
        self.assertEqual(mx.preference, 0)
        self.assertEqual(str(mx.name), "the.email.test.domain")

    def testSimpleFailure(self):
        self.mx.fallbackToDomain = False
        return self.assertFailure(self.mx.getMX("test.domain"), IOError)

    def testSimpleFailureWithFallback(self):
        return self.assertFailure(self.mx.getMX("test.domain"), DNSLookupError)

    def _exchangeTest(self, domain, records, correctMailExchange):
        """
        Issue an MX request for the given domain and arrange for it to be
        responded to with the given records.  Verify that the resulting mail
        exchange is the indicated host.

        @type domain: C{str}
        @type records: C{list} of L{RRHeader}
        @type correctMailExchange: C{str}
        @rtype: L{Deferred}
        """

        class DummyResolver:
            def lookupMailExchange(self, name):
                if name == domain:
                    return defer.succeed((records, [], []))
                return defer.fail(DNSNameError(domain))

        self.mx.resolver = DummyResolver()
        d = self.mx.getMX(domain)

        def gotMailExchange(record):
            self.assertEqual(str(record.name), correctMailExchange)

        d.addCallback(gotMailExchange)
        return d

    def test_mailExchangePreference(self):
        """
        The MX record with the lowest preference is returned by
        L{MXCalculator.getMX}.
        """
        domain = "example.com"
        good = "good.example.com"
        bad = "bad.example.com"

        records = [
            RRHeader(name=domain, type=Record_MX.TYPE, payload=Record_MX(1, bad)),
            RRHeader(name=domain, type=Record_MX.TYPE, payload=Record_MX(0, good)),
            RRHeader(name=domain, type=Record_MX.TYPE, payload=Record_MX(2, bad)),
        ]
        return self._exchangeTest(domain, records, good)

    def test_badExchangeExcluded(self):
        """
        L{MXCalculator.getMX} returns the MX record with the lowest preference
        which is not also marked as bad.
        """
        domain = "example.com"
        good = "good.example.com"
        bad = "bad.example.com"

        records = [
            RRHeader(name=domain, type=Record_MX.TYPE, payload=Record_MX(0, bad)),
            RRHeader(name=domain, type=Record_MX.TYPE, payload=Record_MX(1, good)),
        ]
        self.mx.markBad(bad)
        return self._exchangeTest(domain, records, good)

    def test_fallbackForAllBadExchanges(self):
        """
        L{MXCalculator.getMX} returns the MX record with the lowest preference
        if all the MX records in the response have been marked bad.
        """
        domain = "example.com"
        bad = "bad.example.com"
        worse = "worse.example.com"

        records = [
            RRHeader(name=domain, type=Record_MX.TYPE, payload=Record_MX(0, bad)),
            RRHeader(name=domain, type=Record_MX.TYPE, payload=Record_MX(1, worse)),
        ]
        self.mx.markBad(bad)
        self.mx.markBad(worse)
        return self._exchangeTest(domain, records, bad)

    def test_badExchangeExpires(self):
        """
        L{MXCalculator.getMX} returns the MX record with the lowest preference
        if it was last marked bad longer than L{MXCalculator.timeOutBadMX}
        seconds ago.
        """
        domain = "example.com"
        good = "good.example.com"
        previouslyBad = "bad.example.com"

        records = [
            RRHeader(
                name=domain, type=Record_MX.TYPE, payload=Record_MX(0, previouslyBad)
            ),
            RRHeader(name=domain, type=Record_MX.TYPE, payload=Record_MX(1, good)),
        ]
        self.mx.markBad(previouslyBad)
        self.clock.advance(self.mx.timeOutBadMX)
        return self._exchangeTest(domain, records, previouslyBad)

    def test_goodExchangeUsed(self):
        """
        L{MXCalculator.getMX} returns the MX record with the lowest preference
        if it was marked good after it was marked bad.
        """
        domain = "example.com"
        good = "good.example.com"
        previouslyBad = "bad.example.com"

        records = [
            RRHeader(
                name=domain, type=Record_MX.TYPE, payload=Record_MX(0, previouslyBad)
            ),
            RRHeader(name=domain, type=Record_MX.TYPE, payload=Record_MX(1, good)),
        ]
        self.mx.markBad(previouslyBad)
        self.mx.markGood(previouslyBad)
        self.clock.advance(self.mx.timeOutBadMX)
        return self._exchangeTest(domain, records, previouslyBad)

    def test_successWithoutResults(self):
        """
        If an MX lookup succeeds but the result set is empty,
        L{MXCalculator.getMX} should try to look up an I{A} record for the
        requested name and call back its returned Deferred with that
        address.
        """
        ip = "1.2.3.4"
        domain = "example.org"

        class DummyResolver:
            """
            Fake resolver which will respond to an MX lookup with an empty
            result set.

            @ivar mx: A dictionary mapping hostnames to three-tuples of
                results to be returned from I{MX} lookups.

            @ivar a: A dictionary mapping hostnames to addresses to be
                returned from I{A} lookups.
            """

            mx = {domain: ([], [], [])}
            a = {domain: ip}

            def lookupMailExchange(self, domain):
                return defer.succeed(self.mx[domain])

            def getHostByName(self, domain):
                return defer.succeed(self.a[domain])

        self.mx.resolver = DummyResolver()
        d = self.mx.getMX(domain)
        d.addCallback(self.assertEqual, Record_MX(name=ip))
        return d

    def test_failureWithSuccessfulFallback(self):
        """
        Test that if the MX record lookup fails, fallback is enabled, and an A
        record is available for the name, then the Deferred returned by
        L{MXCalculator.getMX} ultimately fires with a Record_MX instance which
        gives the address in the A record for the name.
        """

        class DummyResolver:
            """
            Fake resolver which will fail an MX lookup but then succeed a
            getHostByName call.
            """

            def lookupMailExchange(self, domain):
                return defer.fail(DNSNameError())

            def getHostByName(self, domain):
                return defer.succeed("1.2.3.4")

        self.mx.resolver = DummyResolver()
        d = self.mx.getMX("domain")
        d.addCallback(self.assertEqual, Record_MX(name="1.2.3.4"))
        return d

    def test_cnameWithoutGlueRecords(self):
        """
        If an MX lookup returns a single CNAME record as a result, MXCalculator
        will perform an MX lookup for the canonical name indicated and return
        the MX record which results.
        """
        alias = "alias.example.com"
        canonical = "canonical.example.com"
        exchange = "mail.example.com"

        class DummyResolver:
            """
            Fake resolver which will return a CNAME for an MX lookup of a name
            which is an alias and an MX for an MX lookup of the canonical name.
            """

            def lookupMailExchange(self, domain):
                if domain == alias:
                    return defer.succeed(
                        (
                            [
                                RRHeader(
                                    name=domain,
                                    type=Record_CNAME.TYPE,
                                    payload=Record_CNAME(canonical),
                                )
                            ],
                            [],
                            [],
                        )
                    )
                elif domain == canonical:
                    return defer.succeed(
                        (
                            [
                                RRHeader(
                                    name=domain,
                                    type=Record_MX.TYPE,
                                    payload=Record_MX(0, exchange),
                                )
                            ],
                            [],
                            [],
                        )
                    )
                else:
                    return defer.fail(DNSNameError(domain))

        self.mx.resolver = DummyResolver()
        d = self.mx.getMX(alias)
        d.addCallback(self.assertEqual, Record_MX(name=exchange))
        return d

    def test_cnameChain(self):
        """
        If L{MXCalculator.getMX} encounters a CNAME chain which is longer than
        the length specified, the returned L{Deferred} should errback with
        L{CanonicalNameChainTooLong}.
        """

        class DummyResolver:
            """
            Fake resolver which generates a CNAME chain of infinite length in
            response to MX lookups.
            """

            chainCounter = 0

            def lookupMailExchange(self, domain):
                self.chainCounter += 1
                name = "x-%d.example.com" % (self.chainCounter,)
                return defer.succeed(
                    (
                        [
                            RRHeader(
                                name=domain,
                                type=Record_CNAME.TYPE,
                                payload=Record_CNAME(name),
                            )
                        ],
                        [],
                        [],
                    )
                )

        cnameLimit = 3
        self.mx.resolver = DummyResolver()
        d = self.mx.getMX("mail.example.com", cnameLimit)
        self.assertFailure(d, twisted.mail.relaymanager.CanonicalNameChainTooLong)

        def cbChainTooLong(error):
            self.assertEqual(
                error.args[0], Record_CNAME("x-%d.example.com" % (cnameLimit + 1,))
            )
            self.assertEqual(self.mx.resolver.chainCounter, cnameLimit + 1)

        d.addCallback(cbChainTooLong)
        return d

    def test_cnameWithGlueRecords(self):
        """
        If an MX lookup returns a CNAME and the MX record for the CNAME, the
        L{Deferred} returned by L{MXCalculator.getMX} should be called back
        with the name from the MX record without further lookups being
        attempted.
        """
        lookedUp = []
        alias = "alias.example.com"
        canonical = "canonical.example.com"
        exchange = "mail.example.com"

        class DummyResolver:
            def lookupMailExchange(self, domain):
                if domain != alias or lookedUp:
                    # Don't give back any results for anything except the alias
                    # or on any request after the first.
                    return ([], [], [])
                return defer.succeed(
                    (
                        [
                            RRHeader(
                                name=alias,
                                type=Record_CNAME.TYPE,
                                payload=Record_CNAME(canonical),
                            ),
                            RRHeader(
                                name=canonical,
                                type=Record_MX.TYPE,
                                payload=Record_MX(name=exchange),
                            ),
                        ],
                        [],
                        [],
                    )
                )

        self.mx.resolver = DummyResolver()
        d = self.mx.getMX(alias)
        d.addCallback(self.assertEqual, Record_MX(name=exchange))
        return d

    def test_cnameLoopWithGlueRecords(self):
        """
        If an MX lookup returns two CNAME records which point to each other,
        the loop should be detected and the L{Deferred} returned by
        L{MXCalculator.getMX} should be errbacked with L{CanonicalNameLoop}.
        """
        firstAlias = "cname1.example.com"
        secondAlias = "cname2.example.com"

        class DummyResolver:
            def lookupMailExchange(self, domain):
                return defer.succeed(
                    (
                        [
                            RRHeader(
                                name=firstAlias,
                                type=Record_CNAME.TYPE,
                                payload=Record_CNAME(secondAlias),
                            ),
                            RRHeader(
                                name=secondAlias,
                                type=Record_CNAME.TYPE,
                                payload=Record_CNAME(firstAlias),
                            ),
                        ],
                        [],
                        [],
                    )
                )

        self.mx.resolver = DummyResolver()
        d = self.mx.getMX(firstAlias)
        self.assertFailure(d, twisted.mail.relaymanager.CanonicalNameLoop)
        return d

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testManyRecords(self):
        self.auth.addresses["test.domain"] = [
            "mx1.test.domain",
            "mx2.test.domain",
            "mx3.test.domain",
        ]
        return self.mx.getMX("test.domain").addCallback(
            self._cbManyRecordsSuccessfulLookup
        )

    def _cbManyRecordsSuccessfulLookup(self, mx):
        self.assertTrue(str(mx.name).split(".", 1)[0] in ("mx1", "mx2", "mx3"))
        self.mx.markBad(str(mx.name))
        return self.mx.getMX("test.domain").addCallback(
            self._cbManyRecordsDifferentResult, mx
        )

    def _cbManyRecordsDifferentResult(self, nextMX, mx):
        self.assertNotEqual(str(mx.name), str(nextMX.name))
        self.mx.markBad(str(nextMX.name))

        return self.mx.getMX("test.domain").addCallback(
            self._cbManyRecordsLastResult, mx, nextMX
        )

    def _cbManyRecordsLastResult(self, lastMX, mx, nextMX):
        self.assertNotEqual(str(mx.name), str(lastMX.name))
        self.assertNotEqual(str(nextMX.name), str(lastMX.name))

        self.mx.markBad(str(lastMX.name))
        self.mx.markGood(str(nextMX.name))

        return self.mx.getMX("test.domain").addCallback(
            self._cbManyRecordsRepeatSpecificResult, nextMX
        )

    def _cbManyRecordsRepeatSpecificResult(self, againMX, nextMX):
        self.assertEqual(str(againMX.name), str(nextMX.name))


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class LiveFireExerciseTests(TestCase):
    if interfaces.IReactorUDP(reactor, None) is None:
        skip = "UDP support is required to determining MX records"

    def setUp(self):
        setUpDNS(self)
        self.tmpdirs = [
            "domainDir",
            "insertionDomain",
            "insertionQueue",
            "destinationDomain",
            "destinationQueue",
        ]

    def tearDown(self):
        for d in self.tmpdirs:
            if os.path.exists(d):
                shutil.rmtree(d)
        return tearDownDNS(self)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testLocalDelivery(self):
        service = mail.mail.MailService()
        service.smtpPortal.registerChecker(cred.checkers.AllowAnonymousAccess())
        domain = mail.maildir.MaildirDirdbmDomain(service, "domainDir")
        domain.addUser("user", "password")
        service.addDomain("test.domain", domain)
        service.portals[""] = service.portals["test.domain"]
        map(service.portals[""].registerChecker, domain.getCredentialsCheckers())

        service.setQueue(mail.relay.DomainQueuer(service))

        f = service.getSMTPFactory()

        self.smtpServer = reactor.listenTCP(0, f, interface="127.0.0.1")

        client = LineSendingProtocol(
            [
                "HELO meson",
                "MAIL FROM: <user@hostname>",
                "RCPT TO: <user@test.domain>",
                "DATA",
                "This is the message",
                ".",
                "QUIT",
            ]
        )

        done = Deferred()
        f = protocol.ClientFactory()
        f.protocol = lambda: client
        f.clientConnectionLost = lambda *args: done.callback(None)
        reactor.connectTCP("127.0.0.1", self.smtpServer.getHost().port, f)

        def finished(ign):
            mbox = domain.requestAvatar("user", None, pop3.IMailbox)[1]
            msg = mbox.getMessage(0).read()
            self.assertNotEqual(msg.find("This is the message"), -1)

            return self.smtpServer.stopListening()

        done.addCallback(finished)
        return done

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testRelayDelivery(self):
        # Here is the service we will connect to and send mail from
        insServ = mail.mail.MailService()
        insServ.smtpPortal.registerChecker(cred.checkers.AllowAnonymousAccess())
        domain = mail.maildir.MaildirDirdbmDomain(insServ, "insertionDomain")
        insServ.addDomain("insertion.domain", domain)
        os.mkdir("insertionQueue")
        insServ.setQueue(mail.relaymanager.Queue("insertionQueue"))
        insServ.domains.setDefaultDomain(mail.relay.DomainQueuer(insServ))
        manager = mail.relaymanager.SmartHostSMTPRelayingManager(insServ.queue)
        manager.fArgs += ("test.identity.hostname",)
        helper = mail.relaymanager.RelayStateHelper(manager, 1)
        # Yoink!  Now the internet obeys OUR every whim!
        manager.mxcalc = mail.relaymanager.MXCalculator(self.resolver)
        # And this is our whim.
        self.auth.addresses["destination.domain"] = ["127.0.0.1"]

        f = insServ.getSMTPFactory()
        self.insServer = reactor.listenTCP(0, f, interface="127.0.0.1")

        # Here is the service the previous one will connect to for final
        # delivery
        destServ = mail.mail.MailService()
        destServ.smtpPortal.registerChecker(cred.checkers.AllowAnonymousAccess())
        domain = mail.maildir.MaildirDirdbmDomain(destServ, "destinationDomain")
        domain.addUser("user", "password")
        destServ.addDomain("destination.domain", domain)
        os.mkdir("destinationQueue")
        destServ.setQueue(mail.relaymanager.Queue("destinationQueue"))
        helper = mail.relaymanager.RelayStateHelper(manager, 1)
        helper.startService()

        f = destServ.getSMTPFactory()
        self.destServer = reactor.listenTCP(0, f, interface="127.0.0.1")

        # Update the port number the *first* relay will connect to, because we can't use
        # port 25
        manager.PORT = self.destServer.getHost().port

        client = LineSendingProtocol(
            [
                "HELO meson",
                "MAIL FROM: <user@wherever>",
                "RCPT TO: <user@destination.domain>",
                "DATA",
                "This is the message",
                ".",
                "QUIT",
            ]
        )

        done = Deferred()
        f = protocol.ClientFactory()
        f.protocol = lambda: client
        f.clientConnectionLost = lambda *args: done.callback(None)
        reactor.connectTCP("127.0.0.1", self.insServer.getHost().port, f)

        def finished(ign):
            # First part of the delivery is done.  Poke the queue manually now
            # so we don't have to wait for the queue to be flushed.
            delivery = manager.checkState()

            def delivered(ign):
                mbox = domain.requestAvatar("user", None, pop3.IMailbox)[1]
                msg = mbox.getMessage(0).read()
                self.assertNotEqual(msg.find("This is the message"), -1)

                self.insServer.stopListening()
                self.destServer.stopListening()
                helper.stopService()

            delivery.addCallback(delivered)
            return delivery

        done.addCallback(finished)
        return done


class LineBufferMessage:
    def __init__(self):
        self.lines = []
        self.eom = False
        self.lost = False

    def lineReceived(self, line):
        self.lines.append(line)

    def eomReceived(self):
        self.eom = True
        return defer.succeed("<Whatever>")

    def connectionLost(self):
        self.lost = True


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class AliasTests(TestCase):
    lines = ["First line", "Next line", "", "After a blank line", "Last line"]

    def testHandle(self):
        result = {}
        lines = [
            "user:  another@host\n",
            "nextuser:  |/bin/program\n",
            "user:  me@again\n",
            "moreusers: :/etc/include/filename\n",
            "multiuser: first@host, second@host,last@anotherhost",
        ]

        for l in lines:
            mail.alias.handle(result, l, "TestCase", None)

        self.assertEqual(result["user"], ["another@host", "me@again"])
        self.assertEqual(result["nextuser"], ["|/bin/program"])
        self.assertEqual(result["moreusers"], [":/etc/include/filename"])
        self.assertEqual(
            result["multiuser"], ["first@host", "second@host", "last@anotherhost"]
        )

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testFileLoader(self):
        domains = {"": object()}
        result = mail.alias.loadAliasFile(
            domains,
            fp=io.BytesIO(
                textwrap.dedent(
                    """\
                    # Here's a comment
                       # woop another one
                    testuser:                   address1,address2, address3,
                        continuation@address, |/bin/process/this

                    usertwo:thisaddress,thataddress, lastaddress
                    lastuser:       :/includable, /filename, |/program, address
                    """
                ).encode()
            ),
        )

        self.assertEqual(len(result), 3)

        group = result["testuser"]
        s = str(group)
        for a in (
            "address1",
            "address2",
            "address3",
            "continuation@address",
            "/bin/process/this",
        ):
            self.assertNotEqual(s.find(a), -1)
        self.assertEqual(len(group), 5)

        group = result["usertwo"]
        s = str(group)
        for a in ("thisaddress", "thataddress", "lastaddress"):
            self.assertNotEqual(s.find(a), -1)
        self.assertEqual(len(group), 3)

        group = result["lastuser"]
        s = str(group)
        self.assertEqual(s.find("/includable"), -1)
        for a in ("/filename", "program", "address"):
            self.assertNotEqual(s.find(a), -1, "%s not found" % a)
        self.assertEqual(len(group), 3)

    def testMultiWrapper(self):
        msgs = LineBufferMessage(), LineBufferMessage(), LineBufferMessage()
        msg = mail.alias.MultiWrapper(msgs)

        for L in self.lines:
            msg.lineReceived(L)
        return msg.eomReceived().addCallback(self._cbMultiWrapper, msgs)

    def _cbMultiWrapper(self, ignored, msgs):
        for m in msgs:
            self.assertTrue(m.eom)
            self.assertFalse(m.lost)
            self.assertEqual(self.lines, m.lines)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def testFileAlias(self):
        tmpfile = self.mktemp()
        a = mail.alias.FileAlias(tmpfile, None, None)
        m = a.createMessageReceiver()

        for l in self.lines:
            m.lineReceived(l)
        return m.eomReceived().addCallback(self._cbTestFileAlias, tmpfile)

    def _cbTestFileAlias(self, ignored, tmpfile):
        with open(tmpfile) as f:
            lines = f.readlines()
        self.assertEqual([L[:-1] for L in lines], self.lines)


class DummyDomain:
    """
    Test domain for L{AddressAliasTests}.
    """

    def __init__(self, address):
        self.address = address

    def exists(self, user, memo=None):
        """
        @returns: When a C{memo} is passed in this will raise a
            L{smtp.SMTPBadRcpt} exception, otherwise a boolean
            indicating if the C{user} and string version of
            L{self.address} are equal or not.
        @rtype: C{bool}
        """
        if memo:
            raise mail.smtp.SMTPBadRcpt("ham")

        return lambda: user == str(self.address)


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class AddressAliasTests(TestCase):
    """
    Tests for L{twisted.mail.alias.AddressAlias}.
    """

    def setUp(self):
        """
        Setup an L{AddressAlias}.
        """
        self.address = mail.smtp.Address("foo@bar")
        domains = {self.address.domain: DummyDomain(self.address)}
        self.alias = mail.alias.AddressAlias(self.address, domains, self.address)

    def test_createMessageReceiver(self):
        """
        L{createMessageReceiever} calls C{exists()} on the domain object
        which key matches the C{alias} passed to L{AddressAlias}.
        """
        self.assertTrue(self.alias.createMessageReceiver())

    def test_str(self):
        """
        The string presentation of L{AddressAlias} includes the alias.
        """
        self.assertEqual(str(self.alias), "<Address foo@bar>")

    def test_resolve(self):
        """
        L{resolve} will look for additional aliases when an C{aliasmap}
        dictionary is passed, and returns L{None} if none were found.
        """
        self.assertEqual(self.alias.resolve({self.address: "bar"}), None)

    def test_resolveWithoutAliasmap(self):
        """
        L{resolve} returns L{None} when the alias could not be found in the
        C{aliasmap} and no L{mail.smtp.User} with this alias exists either.
        """
        self.assertEqual(self.alias.resolve({}), None)


class DummyProcess:
    __slots__ = ["onEnd"]


class MockProcessAlias(mail.alias.ProcessAlias):
    """
    An alias processor that doesn't actually launch processes.
    """

    def spawnProcess(self, proto, program, path):
        """
        Don't spawn a process.
        """


class MockAliasGroup(mail.alias.AliasGroup):
    """
    An alias group using C{MockProcessAlias}.
    """

    processAliasFactory = MockProcessAlias


class StubProcess:
    """
    Fake implementation of L{IProcessTransport}.

    @ivar signals: A list of all the signals which have been sent to this fake
        process.
    """

    def __init__(self):
        self.signals = []

    def loseConnection(self):
        """
        No-op implementation of disconnection.
        """

    def signalProcess(self, signal):
        """
        Record a signal sent to this process for later inspection.
        """
        self.signals.append(signal)


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class ProcessAliasTests(TestCase):
    """
    Tests for alias resolution.
    """

    if interfaces.IReactorProcess(reactor, None) is None:
        skip = "IReactorProcess not supported"

    lines = ["First line", "Next line", "", "After a blank line", "Last line"]

    def exitStatus(self, code):
        """
        Construct a status from the given exit code.

        @type code: L{int} between 0 and 255 inclusive.
        @param code: The exit status which the code will represent.

        @rtype: L{int}
        @return: A status integer for the given exit code.
        """
        # /* Macros for constructing status values.  */
        # #define __W_EXITCODE(ret, sig)  ((ret) << 8 | (sig))
        status = (code << 8) | 0

        # Sanity check
        self.assertTrue(os.WIFEXITED(status))
        self.assertEqual(os.WEXITSTATUS(status), code)
        self.assertFalse(os.WIFSIGNALED(status))

        return status

    def signalStatus(self, signal):
        """
        Construct a status from the given signal.

        @type signal: L{int} between 0 and 255 inclusive.
        @param signal: The signal number which the status will represent.

        @rtype: L{int}
        @return: A status integer for the given signal.
        """
        # /* If WIFSIGNALED(STATUS), the terminating signal.  */
        # #define __WTERMSIG(status)      ((status) & 0x7f)
        # /* Nonzero if STATUS indicates termination by a signal.  */
        # #define __WIFSIGNALED(status) \
        #    (((signed char) (((status) & 0x7f) + 1) >> 1) > 0)
        status = signal

        # Sanity check
        self.assertTrue(os.WIFSIGNALED(status))
        self.assertEqual(os.WTERMSIG(status), signal)
        self.assertFalse(os.WIFEXITED(status))

        return status

    def setUp(self):
        """
        Replace L{smtp.DNSNAME} with a well-known value.
        """
        self.DNSNAME = smtp.DNSNAME
        smtp.DNSNAME = ""

    def tearDown(self):
        """
        Restore the original value of L{smtp.DNSNAME}.
        """
        smtp.DNSNAME = self.DNSNAME

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_processAlias(self):
        """
        Standard call to C{mail.alias.ProcessAlias}: check that the specified
        script is called, and that the input is correctly transferred to it.
        """
        sh = FilePath(self.mktemp())
        sh.setContent(
            """\
#!/bin/sh
rm -f process.alias.out
while read i; do
    echo $i >> process.alias.out
done"""
        )
        os.chmod(sh.path, 0o700)
        a = mail.alias.ProcessAlias(sh.path, None, None)
        m = a.createMessageReceiver()

        for l in self.lines:
            m.lineReceived(l)

        def _cbProcessAlias(ignored):
            with open("process.alias.out") as f:
                lines = f.readlines()
            self.assertEqual([L[:-1] for L in lines], self.lines)

        return m.eomReceived().addCallback(_cbProcessAlias)

    def test_processAliasTimeout(self):
        """
        If the alias child process does not exit within a particular period of
        time, the L{Deferred} returned by L{MessageWrapper.eomReceived} should
        fail with L{ProcessAliasTimeout} and send the I{KILL} signal to the
        child process..
        """
        reactor = task.Clock()
        transport = StubProcess()
        proto = mail.alias.ProcessAliasProtocol()
        proto.makeConnection(transport)

        receiver = mail.alias.MessageWrapper(proto, None, reactor)
        d = receiver.eomReceived()
        reactor.advance(receiver.completionTimeout)

        def timedOut(ignored):
            self.assertEqual(transport.signals, ["KILL"])
            # Now that it has been killed, disconnect the protocol associated
            # with it.
            proto.processEnded(ProcessTerminated(self.signalStatus(signal.SIGKILL)))

        self.assertFailure(d, mail.alias.ProcessAliasTimeout)
        d.addCallback(timedOut)
        return d

    def test_earlyProcessTermination(self):
        """
        If the process associated with an L{mail.alias.MessageWrapper} exits
        before I{eomReceived} is called, the L{Deferred} returned by
        I{eomReceived} should fail.
        """
        transport = StubProcess()
        protocol = mail.alias.ProcessAliasProtocol()
        protocol.makeConnection(transport)
        receiver = mail.alias.MessageWrapper(protocol, None, None)
        protocol.processEnded(failure.Failure(ProcessDone(0)))
        return self.assertFailure(receiver.eomReceived(), ProcessDone)

    def _terminationTest(self, status):
        """
        Verify that if the process associated with an
        L{mail.alias.MessageWrapper} exits with the given status, the
        L{Deferred} returned by I{eomReceived} fails with L{ProcessTerminated}.
        """
        transport = StubProcess()
        protocol = mail.alias.ProcessAliasProtocol()
        protocol.makeConnection(transport)
        receiver = mail.alias.MessageWrapper(protocol, None, None)
        protocol.processEnded(failure.Failure(ProcessTerminated(status)))
        return self.assertFailure(receiver.eomReceived(), ProcessTerminated)

    def test_errorProcessTermination(self):
        """
        If the process associated with an L{mail.alias.MessageWrapper} exits
        with a non-zero exit code, the L{Deferred} returned by I{eomReceived}
        should fail.
        """
        return self._terminationTest(self.exitStatus(1))

    def test_signalProcessTermination(self):
        """
        If the process associated with an L{mail.alias.MessageWrapper} exits
        because it received a signal, the L{Deferred} returned by
        I{eomReceived} should fail.
        """
        return self._terminationTest(self.signalStatus(signal.SIGHUP))

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_aliasResolution(self):
        """
        Check that the C{resolve} method of alias processors produce the correct
        set of objects:
            - direct alias with L{mail.alias.AddressAlias} if a simple input is passed
            - aliases in a file with L{mail.alias.FileWrapper} if an input in the format
              '/file' is given
            - aliases resulting of a process call wrapped by L{mail.alias.MessageWrapper}
              if the format is '|process'
        """
        aliases = {}
        domain = {"": TestDomain(aliases, ["user1", "user2", "user3"])}
        A1 = MockAliasGroup(["user1", "|echo", "/file"], domain, "alias1")
        A2 = MockAliasGroup(["user2", "user3"], domain, "alias2")
        A3 = mail.alias.AddressAlias("alias1", domain, "alias3")
        aliases.update(
            {
                "alias1": A1,
                "alias2": A2,
                "alias3": A3,
            }
        )

        res1 = A1.resolve(aliases)
        r1 = map(str, res1.objs)
        r1.sort()
        expected = map(
            str,
            [
                mail.alias.AddressAlias("user1", None, None),
                mail.alias.MessageWrapper(DummyProcess(), "echo"),
                mail.alias.FileWrapper("/file"),
            ],
        )
        expected.sort()
        self.assertEqual(r1, expected)

        res2 = A2.resolve(aliases)
        r2 = map(str, res2.objs)
        r2.sort()
        expected = map(
            str,
            [
                mail.alias.AddressAlias("user2", None, None),
                mail.alias.AddressAlias("user3", None, None),
            ],
        )
        expected.sort()
        self.assertEqual(r2, expected)

        res3 = A3.resolve(aliases)
        r3 = map(str, res3.objs)
        r3.sort()
        expected = map(
            str,
            [
                mail.alias.AddressAlias("user1", None, None),
                mail.alias.MessageWrapper(DummyProcess(), "echo"),
                mail.alias.FileWrapper("/file"),
            ],
        )
        expected.sort()
        self.assertEqual(r3, expected)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_cyclicAlias(self):
        """
        Check that a cycle in alias resolution is correctly handled.
        """
        aliases = {}
        domain = {"": TestDomain(aliases, [])}
        A1 = mail.alias.AddressAlias("alias2", domain, "alias1")
        A2 = mail.alias.AddressAlias("alias3", domain, "alias2")
        A3 = mail.alias.AddressAlias("alias1", domain, "alias3")
        aliases.update({"alias1": A1, "alias2": A2, "alias3": A3})

        self.assertEqual(aliases["alias1"].resolve(aliases), None)
        self.assertEqual(aliases["alias2"].resolve(aliases), None)
        self.assertEqual(aliases["alias3"].resolve(aliases), None)

        A4 = MockAliasGroup(["|echo", "alias1"], domain, "alias4")
        aliases["alias4"] = A4

        res = A4.resolve(aliases)
        r = map(str, res.objs)
        r.sort()
        expected = map(str, [mail.alias.MessageWrapper(DummyProcess(), "echo")])
        expected.sort()
        self.assertEqual(r, expected)


class TestDomain:
    def __init__(self, aliases, users):
        self.aliases = aliases
        self.users = users

    def exists(self, user, memo=None):
        user = user.dest.local
        if user in self.users:
            return lambda: mail.alias.AddressAlias(user, None, None)
        try:
            a = self.aliases[user]
        except BaseException:
            raise smtp.SMTPBadRcpt(user)
        else:
            aliases = a.resolve(self.aliases, memo)
            if aliases:
                return lambda: aliases
            raise smtp.SMTPBadRcpt(user)


class DummyQueue:
    """
    A fake relay queue to use for testing.

    This queue doesn't keep track of which messages are waiting to be relayed
    or are in the process of being relayed.

    @ivar directory: See L{__init__}.
    """

    def __init__(self, directory):
        """
        @type directory: L{bytes}
        @param directory: The pathname of the directory holding messages in the
            queue.
        """
        self.directory = directory

    def done(self, message):
        """
        Remove a message from the queue.

        @type message: L{bytes}
        @param message: The base filename of a message.
        """
        message = os.path.basename(message)
        os.remove(self.getPath(message) + "-D")
        os.remove(self.getPath(message) + "-H")

    def getEnvelopeFile(self, message):
        """
        Get the envelope file for a message in the queue.

        @type message: L{bytes}
        @param message: The base filename of a message.

        @rtype: L{file}
        @return: The envelope file for the message.
        """
        return open(os.path.join(self.directory, message + "-H"), "rb")

    def getPath(self, message):
        """
        Return the full base pathname of a message in the queue.

        @type message: L{bytes}
        @param message: The base filename of a message.

        @rtype: L{bytes}
        @return: The full base pathname of the message.
        """
        return os.path.join(self.directory, message)

    def createNewMessage(self):
        """
        Create a new message in the queue.

        @rtype: 2-L{tuple} of (E{1}) L{file}, (E{2}) L{FileMessage}
        @return: The envelope file and a message receiver for a new message in
            the queue.
        """
        fname = f"{time.time()}_{id(self)}"
        headerFile = open(os.path.join(self.directory, fname + "-H"), "wb")
        tempFilename = os.path.join(self.directory, fname + "-C")
        finalFilename = os.path.join(self.directory, fname + "-D")
        messageFile = open(tempFilename, "wb")

        return headerFile, mail.mail.FileMessage(
            messageFile, tempFilename, finalFilename
        )

    def setWaiting(self, message):
        """
        Ignore the request to mark a message as waiting to be relayed.

        @type message: L{bytes}
        @param message: The base filename of a message.
        """
        pass


class DummySmartHostSMTPRelayingManager:
    """
    A fake smart host to use for testing.

    @type managed: L{dict} of L{bytes} -> L{list} of
        L{list} of L{bytes}
    @ivar managed: A mapping of a string identifying a managed relayer to
        filenames of messages the managed relayer is responsible for.

    @ivar queue: See L{__init__}.
    """

    def __init__(self, queue):
        """
        Initialize the minimum necessary members of a smart host.

        @type queue: L{DummyQueue}
        @param queue: A queue that can be used for testing purposes.
        """
        self.managed = {}
        self.queue = queue


@skipIf(platformType != "posix", "twisted.mail only works on posix")
class _AttemptManagerTests(TestCase):
    """
    Test the behavior of L{_AttemptManager}.

    @type tmpdir: L{bytes}
    @ivar tmpdir: The path to a temporary directory holding the message files.

    @type reactor: L{MemoryReactorClock}
    @ivar reactor: The reactor used for test purposes.

    @type eventLog: L{None} or L{dict} of L{bytes} -> L{object}
    @ivar eventLog: Information about the last informational log message
        generated or none if no log message has been generated.

    @type noisyAttemptMgr: L{_AttemptManager}
    @ivar noisyAttemptMgr: An attempt manager which generates informational
        log messages.

    @type quietAttemptMgr: L{_AttemptManager}
    @ivar quietAttemptMgr: An attempt manager which does not generate
        informational log messages.

    @type noisyMessage: L{bytes}
    @ivar noisyMessage: The full base pathname of the message to be used with
        the noisy attempt manager.

    @type quietMessage: L{bytes}
    @ivar quietMessage: The full base pathname of the message to be used with
        the quiet.
    """

    def setUp(self):
        """
        Set up a temporary directory for the queue, attempt managers with the
        noisy flag on and off, message files for use with each attempt manager,
        and a reactor.  Also, register to be notified when log messages are
        generated.
        """
        self.tmpdir = self.mktemp()
        os.mkdir(self.tmpdir)

        self.reactor = MemoryReactorClock()

        self.eventLog = None
        log.addObserver(self._logObserver)

        self.noisyAttemptMgr = _AttemptManager(
            DummySmartHostSMTPRelayingManager(DummyQueue(self.tmpdir)),
            True,
            self.reactor,
        )
        self.quietAttemptMgr = _AttemptManager(
            DummySmartHostSMTPRelayingManager(DummyQueue(self.tmpdir)),
            False,
            self.reactor,
        )

        noisyBaseName = "noisyMessage"
        quietBaseName = "quietMessage"

        self.noisyMessage = os.path.join(self.tmpdir, noisyBaseName)
        self.quietMessage = os.path.join(self.tmpdir, quietBaseName)

        open(self.noisyMessage + "-D", "w").close()

        open(self.quietMessage + "-D", "w").close()

        self.noisyAttemptMgr.manager.managed["noisyRelayer"] = [noisyBaseName]
        self.quietAttemptMgr.manager.managed["quietRelayer"] = [quietBaseName]

        with open(self.noisyMessage + "-H", "wb") as envelope:
            pickle.dump(["from-noisy@domain", "to-noisy@domain"], envelope)

        with open(self.quietMessage + "-H", "wb") as envelope:
            pickle.dump(["from-quiet@domain", "to-quiet@domain"], envelope)

    def tearDown(self):
        """
        Unregister for log events and remove the temporary directory.
        """
        log.removeObserver(self._logObserver)
        shutil.rmtree(self.tmpdir)

    def _logObserver(self, eventDict):
        """
        A log observer.

        @type eventDict: L{dict} of L{bytes} -> L{object}
        @param eventDict: Information about the last informational log message
            generated.
        """
        self.eventLog = eventDict

    def test_initNoisyDefault(self):
        """
        When an attempt manager is created without the noisy parameter, the
        noisy instance variable should default to true.
        """
        am = _AttemptManager(DummySmartHostSMTPRelayingManager(DummyQueue(self.tmpdir)))
        self.assertTrue(am.noisy)

    def test_initNoisy(self):
        """
        When an attempt manager is created with the noisy parameter set to
        true, the noisy instance variable should be set to true.
        """
        self.assertTrue(self.noisyAttemptMgr.noisy)

    def test_initQuiet(self):
        """
        When an attempt manager is created with the noisy parameter set to
        false, the noisy instance variable should be set to false.
        """
        self.assertFalse(self.quietAttemptMgr.noisy)

    def test_initReactorDefault(self):
        """
        When an attempt manager is created without the reactor parameter, the
        reactor instance variable should default to the global reactor.
        """
        am = _AttemptManager(DummySmartHostSMTPRelayingManager(DummyQueue(self.tmpdir)))
        self.assertEqual(am.reactor, reactor)

    def test_initReactor(self):
        """
        When an attempt manager is created with a reactor provided, the
        reactor instance variable should default to that reactor.
        """
        self.assertEqual(self.noisyAttemptMgr.reactor, self.reactor)

    def test_notifySuccessNoisy(self):
        """
        For an attempt manager with the noisy flag set, notifySuccess should
        result in a log message.
        """
        self.noisyAttemptMgr.notifySuccess("noisyRelayer", self.noisyMessage)
        self.assertTrue(self.eventLog)

    def test_notifySuccessQuiet(self):
        """
        For an attempt manager with the noisy flag not set, notifySuccess
        should result in no log message.
        """
        self.quietAttemptMgr.notifySuccess("quietRelayer", self.quietMessage)
        self.assertFalse(self.eventLog)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_notifyFailureNoisy(self):
        """
        For an attempt manager with the noisy flag set, notifyFailure should
        result in a log message.
        """
        self.noisyAttemptMgr.notifyFailure("noisyRelayer", self.noisyMessage)
        self.assertTrue(self.eventLog)

    @skipIf(sys.version_info >= (3,), "not ported to Python 3")
    def test_notifyFailureQuiet(self):
        """
        For an attempt manager with the noisy flag not set, notifyFailure
        should result in no log message.
        """
        self.quietAttemptMgr.notifyFailure("quietRelayer", self.quietMessage)
        self.assertFalse(self.eventLog)

    def test_notifyDoneNoisy(self):
        """
        For an attempt manager with the noisy flag set, notifyDone should
        result in a log message.
        """
        self.noisyAttemptMgr.notifyDone("noisyRelayer")
        self.assertTrue(self.eventLog)

    def test_notifyDoneQuiet(self):
        """
        For an attempt manager with the noisy flag not set, notifyDone
        should result in no log message.
        """
        self.quietAttemptMgr.notifyDone("quietRelayer")
        self.assertFalse(self.eventLog)

    def test_notifyNoConnectionNoisy(self):
        """
        For an attempt manager with the noisy flag set, notifyNoConnection
        should result in a log message.
        """
        self.noisyAttemptMgr.notifyNoConnection("noisyRelayer")
        self.assertTrue(self.eventLog)
        self.reactor.advance(60)

    def test_notifyNoConnectionQuiet(self):
        """
        For an attempt manager with the noisy flag not set, notifyNoConnection
        should result in no log message.
        """
        self.quietAttemptMgr.notifyNoConnection("quietRelayer")
        self.assertFalse(self.eventLog)
        self.reactor.advance(60)
