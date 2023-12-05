# -*- test-case-name: twisted.mail.test.test_mail -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Maildir-style mailbox support.
"""

import io
import os
import socket
import stat
from hashlib import md5
from typing import IO

from zope.interface import implementer

from twisted.cred import checkers, credentials, portal
from twisted.cred.error import UnauthorizedLogin
from twisted.internet import defer, interfaces, reactor
from twisted.mail import mail, pop3, smtp
from twisted.persisted import dirdbm
from twisted.protocols import basic
from twisted.python import failure, log

INTERNAL_ERROR = """\
From: Twisted.mail Internals
Subject: An Error Occurred

  An internal server error has occurred.  Please contact the
  server administrator.
"""


class _MaildirNameGenerator:
    """
    A utility class to generate a unique maildir name.

    @type n: L{int}
    @ivar n: A counter used to generate unique integers.

    @type p: L{int}
    @ivar p: The ID of the current process.

    @type s: L{bytes}
    @ivar s: A representation of the hostname.

    @ivar _clock: See C{clock} parameter of L{__init__}.
    """

    n = 0
    p = os.getpid()
    s = socket.gethostname().replace("/", r"\057").replace(":", r"\072")

    def __init__(self, clock):
        """
        @type clock: L{IReactorTime <interfaces.IReactorTime>} provider
        @param clock: A reactor which will be used to learn the current time.
        """
        self._clock = clock

    def generate(self):
        """
        Generate a string which is intended to be unique across all calls to
        this function (across all processes, reboots, etc).

        Strings returned by earlier calls to this method will compare less
        than strings returned by later calls as long as the clock provided
        doesn't go backwards.

        @rtype: L{bytes}
        @return: A unique string.
        """
        self.n = self.n + 1
        t = self._clock.seconds()
        seconds = str(int(t))
        microseconds = "%07d" % (int((t - int(t)) * 10e6),)
        return f"{seconds}.M{microseconds}P{self.p}Q{self.n}.{self.s}"


_generateMaildirName = _MaildirNameGenerator(reactor).generate


def initializeMaildir(dir):
    """
    Create a maildir user directory if it doesn't already exist.

    @type dir: L{bytes}
    @param dir: The path name for a user directory.
    """
    dir = os.fsdecode(dir)
    if not os.path.isdir(dir):
        os.mkdir(dir, 0o700)
        for subdir in ["new", "cur", "tmp", ".Trash"]:
            os.mkdir(os.path.join(dir, subdir), 0o700)
        for subdir in ["new", "cur", "tmp"]:
            os.mkdir(os.path.join(dir, ".Trash", subdir), 0o700)
        # touch
        open(os.path.join(dir, ".Trash", "maildirfolder"), "w").close()


class MaildirMessage(mail.FileMessage):
    """
    A message receiver which adds a header and delivers a message to a file
    whose name includes the size of the message.

    @type size: L{int}
    @ivar size: The number of octets in the message.
    """

    size = None

    def __init__(self, address, fp, *a, **kw):
        """
        @type address: L{bytes}
        @param address: The address of the message recipient.

        @type fp: file-like object
        @param fp: The file in which to store the message while it is being
            received.

        @type a: 2-L{tuple} of (0) L{bytes}, (1) L{bytes}
        @param a: Positional arguments for L{FileMessage.__init__}.

        @type kw: L{dict}
        @param kw: Keyword arguments for L{FileMessage.__init__}.
        """
        header = b"Delivered-To: %s\n" % address
        fp.write(header)
        self.size = len(header)
        mail.FileMessage.__init__(self, fp, *a, **kw)

    def lineReceived(self, line):
        """
        Write a line to the file.

        @type line: L{bytes}
        @param line: A received line.
        """
        mail.FileMessage.lineReceived(self, line)
        self.size += len(line) + 1

    def eomReceived(self):
        """
        At the end of message, rename the file holding the message to its final
        name concatenated with the size of the file.

        @rtype: L{Deferred <defer.Deferred>} which successfully results in
            L{bytes}
        @return: A deferred which returns the name of the file holding the
            message.
        """
        self.finalName = self.finalName + ",S=%d" % self.size
        return mail.FileMessage.eomReceived(self)


@implementer(mail.IAliasableDomain)
class AbstractMaildirDomain:
    """
    An abstract maildir-backed domain.

    @type alias: L{None} or L{dict} mapping
        L{bytes} to L{AliasBase}
    @ivar alias: A mapping of username to alias.

    @ivar root: See L{__init__}.
    """

    alias = None
    root = None

    def __init__(self, service, root):
        """
        @type service: L{MailService}
        @param service: An email service.

        @type root: L{bytes}
        @param root: The maildir root directory.
        """
        self.root = root

    def userDirectory(self, user):
        """
        Return the maildir directory for a user.

        @type user: L{bytes}
        @param user: A username.

        @rtype: L{bytes} or L{None}
        @return: The user's mail directory for a valid user. Otherwise,
            L{None}.
        """
        return None

    def setAliasGroup(self, alias):
        """
        Set the group of defined aliases for this domain.

        @type alias: L{dict} mapping L{bytes} to L{IAlias} provider.
        @param alias: A mapping of domain name to alias.
        """
        self.alias = alias

    def exists(self, user, memo=None):
        """
        Check whether a user exists in this domain or an alias of it.

        @type user: L{User}
        @param user: A user.

        @type memo: L{None} or L{dict} of L{AliasBase}
        @param memo: A record of the addresses already considered while
            resolving aliases. The default value should be used by all
            external code.

        @rtype: no-argument callable which returns L{IMessage <smtp.IMessage>}
            provider.
        @return: A function which takes no arguments and returns a message
            receiver for the user.

        @raises SMTPBadRcpt: When the given user does not exist in this domain
            or an alias of it.
        """
        if self.userDirectory(user.dest.local) is not None:
            return lambda: self.startMessage(user)
        try:
            a = self.alias[user.dest.local]
        except BaseException:
            raise smtp.SMTPBadRcpt(user)
        else:
            aliases = a.resolve(self.alias, memo)
            if aliases:
                return lambda: aliases
            log.err("Bad alias configuration: " + str(user))
            raise smtp.SMTPBadRcpt(user)

    def startMessage(self, user):
        """
        Create a maildir message for a user.

        @type user: L{bytes}
        @param user: A username.

        @rtype: L{MaildirMessage}
        @return: A message receiver for this user.
        """
        if isinstance(user, str):
            name, domain = user.split("@", 1)
        else:
            name, domain = user.dest.local, user.dest.domain
        dir = self.userDirectory(name)
        fname = _generateMaildirName()
        filename = os.path.join(dir, "tmp", fname)
        fp = open(filename, "w")
        return MaildirMessage(
            f"{name}@{domain}", fp, filename, os.path.join(dir, "new", fname)
        )

    def willRelay(self, user, protocol):
        """
        Check whether this domain will relay.

        @type user: L{Address}
        @param user: The destination address.

        @type protocol: L{SMTP}
        @param protocol: The protocol over which the message to be relayed is
            being received.

        @rtype: L{bool}
        @return: An indication of whether this domain will relay the message to
            the destination.
        """
        return False

    def addUser(self, user, password):
        """
        Add a user to this domain.

        Subclasses should override this method.

        @type user: L{bytes}
        @param user: A username.

        @type password: L{bytes}
        @param password: A password.
        """
        raise NotImplementedError

    def getCredentialsCheckers(self):
        """
        Return credentials checkers for this domain.

        Subclasses should override this method.

        @rtype: L{list} of L{ICredentialsChecker
            <checkers.ICredentialsChecker>} provider
        @return: Credentials checkers for this domain.
        """
        raise NotImplementedError


@implementer(interfaces.IConsumer)
class _MaildirMailboxAppendMessageTask:
    """
    A task which adds a message to a maildir mailbox.

    @ivar mbox: See L{__init__}.

    @type defer: L{Deferred <defer.Deferred>} which successfully returns
        L{None}
    @ivar defer: A deferred which fires when the task has completed.

    @type opencall: L{IDelayedCall <interfaces.IDelayedCall>} provider or
        L{None}
    @ivar opencall: A scheduled call to L{prodProducer}.

    @type msg: file-like object
    @ivar msg: The message to add.

    @type tmpname: L{bytes}
    @ivar tmpname: The pathname of the temporary file holding the message while
        it is being transferred.

    @type fh: file
    @ivar fh: The new maildir file.

    @type filesender: L{FileSender <basic.FileSender>}
    @ivar filesender: A file sender which sends the message.

    @type myproducer: L{IProducer <interfaces.IProducer>}
    @ivar myproducer: The registered producer.

    @type streaming: L{bool}
    @ivar streaming: Indicates whether the registered producer provides a
        streaming interface.
    """

    osopen = staticmethod(os.open)
    oswrite = staticmethod(os.write)
    osclose = staticmethod(os.close)
    osrename = staticmethod(os.rename)

    def __init__(self, mbox, msg):
        """
        @type mbox: L{MaildirMailbox}
        @param mbox: A maildir mailbox.

        @type msg: L{bytes} or file-like object
        @param msg: The message to add.
        """
        self.mbox = mbox
        self.defer = defer.Deferred()
        self.openCall = None
        if not hasattr(msg, "read"):
            msg = io.BytesIO(msg)
        self.msg = msg

    def startUp(self):
        """
        Start transferring the message to the mailbox.
        """
        self.createTempFile()
        if self.fh != -1:
            self.filesender = basic.FileSender()
            self.filesender.beginFileTransfer(self.msg, self)

    def registerProducer(self, producer, streaming):
        """
        Register a producer and start asking it for data if it is
        non-streaming.

        @type producer: L{IProducer <interfaces.IProducer>}
        @param producer: A producer.

        @type streaming: L{bool}
        @param streaming: A flag indicating whether the producer provides a
            streaming interface.
        """
        self.myproducer = producer
        self.streaming = streaming
        if not streaming:
            self.prodProducer()

    def prodProducer(self):
        """
        Repeatedly prod a non-streaming producer to produce data.
        """
        self.openCall = None
        if self.myproducer is not None:
            self.openCall = reactor.callLater(0, self.prodProducer)
            self.myproducer.resumeProducing()

    def unregisterProducer(self):
        """
        Finish transferring the message to the mailbox.
        """
        self.myproducer = None
        self.streaming = None
        self.osclose(self.fh)
        self.moveFileToNew()

    def write(self, data):
        """
        Write data to the maildir file.

        @type data: L{bytes}
        @param data: Data to be written to the file.
        """
        try:
            self.oswrite(self.fh, data)
        except BaseException:
            self.fail()

    def fail(self, err=None):
        """
        Fire the deferred to indicate the task completed with a failure.

        @type err: L{Failure <failure.Failure>}
        @param err: The error that occurred.
        """
        if err is None:
            err = failure.Failure()
        if self.openCall is not None:
            self.openCall.cancel()
        self.defer.errback(err)
        self.defer = None

    def moveFileToNew(self):
        """
        Place the message in the I{new/} directory, add it to the mailbox and
        fire the deferred to indicate that the task has completed
        successfully.
        """
        while True:
            newname = os.path.join(self.mbox.path, "new", _generateMaildirName())
            try:
                self.osrename(self.tmpname, newname)
                break
            except OSError as e:
                (err, estr) = e.args
                import errno

                # if the newname exists, retry with a new newname.
                if err != errno.EEXIST:
                    self.fail()
                    newname = None
                    break
        if newname is not None:
            self.mbox.list.append(newname)
            self.defer.callback(None)
            self.defer = None

    def createTempFile(self):
        """
        Create a temporary file to hold the message as it is being transferred.
        """
        attr = (
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOINHERIT", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        tries = 0
        self.fh = -1
        while True:
            self.tmpname = os.path.join(self.mbox.path, "tmp", _generateMaildirName())
            try:
                self.fh = self.osopen(self.tmpname, attr, 0o600)
                return None
            except OSError:
                tries += 1
                if tries > 500:
                    self.defer.errback(
                        RuntimeError(
                            "Could not create tmp file for %s" % self.mbox.path
                        )
                    )
                    self.defer = None
                    return None


class MaildirMailbox(pop3.Mailbox):
    """
    A maildir-backed mailbox.

    @ivar path: See L{__init__}.

    @type list: L{list} of L{int} or 2-L{tuple} of (0) file-like object,
        (1) L{bytes}
    @ivar list: Information about the messages in the mailbox. For undeleted
        messages, the file containing the message and the
        full path name of the file are stored.  Deleted messages are indicated
        by 0.

    @type deleted: L{dict} mapping 2-L{tuple} of (0) file-like object,
        (1) L{bytes} to L{bytes}
    @type deleted: A mapping of the information about a file before it was
        deleted to the full path name of the deleted file in the I{.Trash/}
        subfolder.
    """

    AppendFactory = _MaildirMailboxAppendMessageTask

    def __init__(self, path):
        """
        @type path: L{bytes}
        @param path: The directory name for a maildir mailbox.
        """
        self.path = path
        self.list = []
        self.deleted = {}
        initializeMaildir(path)
        for name in ("cur", "new"):
            for file in os.listdir(os.path.join(path, name)):
                self.list.append((file, os.path.join(path, name, file)))
        self.list.sort()
        self.list = [e[1] for e in self.list]

    def listMessages(self, i=None):
        """
        Retrieve the size of a message, or, if none is specified, the size of
        each message in the mailbox.

        @type i: L{int} or L{None}
        @param i: The 0-based index of a message.

        @rtype: L{int} or L{list} of L{int}
        @return: The number of octets in the specified message, or, if an index
            is not specified, a list of the number of octets for all messages
            in the mailbox.  Any value which corresponds to a deleted message
            is set to 0.

        @raise IndexError: When the index does not correspond to a message in
            the mailbox.
        """
        if i is None:
            ret = []
            for mess in self.list:
                if mess:
                    ret.append(os.stat(mess)[stat.ST_SIZE])
                else:
                    ret.append(0)
            return ret
        return self.list[i] and os.stat(self.list[i])[stat.ST_SIZE] or 0

    def getMessage(self, i):
        """
        Retrieve a file-like object with the contents of a message.

        @type i: L{int}
        @param i: The 0-based index of a message.

        @rtype: file-like object
        @return: A file containing the message.

        @raise IndexError: When the index does not correspond to a message in
            the mailbox.
        """
        return open(self.list[i])

    def getUidl(self, i):
        """
        Get a unique identifier for a message.

        @type i: L{int}
        @param i: The 0-based index of a message.

        @rtype: L{bytes}
        @return: A string of printable characters uniquely identifying the
            message for all time.

        @raise IndexError: When the index does not correspond to a message in
            the mailbox.
        """
        # Returning the actual filename is a mistake.  Hash it.
        base = os.path.basename(self.list[i])
        return md5(base).hexdigest()

    def deleteMessage(self, i):
        """
        Mark a message for deletion.

        Move the message to the I{.Trash/} subfolder so it can be undeleted
        by an administrator.

        @type i: L{int}
        @param i: The 0-based index of a message.

        @raise IndexError: When the index does not correspond to a message in
            the mailbox.
        """
        trashFile = os.path.join(
            self.path, ".Trash", "cur", os.path.basename(self.list[i])
        )
        os.rename(self.list[i], trashFile)
        self.deleted[self.list[i]] = trashFile
        self.list[i] = 0

    def undeleteMessages(self):
        """
        Undelete all messages marked for deletion.

        Move each message marked for deletion from the I{.Trash/} subfolder back
        to its original position.
        """
        for (real, trash) in self.deleted.items():
            try:
                os.rename(trash, real)
            except OSError as e:
                (err, estr) = e.args
                import errno

                # If the file has been deleted from disk, oh well!
                if err != errno.ENOENT:
                    raise
                # This is a pass
            else:
                try:
                    self.list[self.list.index(0)] = real
                except ValueError:
                    self.list.append(real)
        self.deleted.clear()

    def appendMessage(self, txt):
        """
        Add a message to the mailbox.

        @type txt: L{bytes} or file-like object
        @param txt: A message to add.

        @rtype: L{Deferred <defer.Deferred>}
        @return: A deferred which fires when the message has been added to
            the mailbox.
        """
        task = self.AppendFactory(self, txt)
        result = task.defer
        task.startUp()
        return result


@implementer(pop3.IMailbox)
class StringListMailbox:
    """
    An in-memory mailbox.

    @ivar  msgs: See L{__init__}.

    @type _delete: L{set} of L{int}
    @ivar _delete: The indices of messages which have been marked for deletion.
    """

    def __init__(self, msgs):
        """
        @type msgs: L{list} of L{bytes}
        @param msgs: The contents of each message in the mailbox.
        """
        self.msgs = msgs
        self._delete = set()

    def listMessages(self, i=None):
        """
        Retrieve the size of a message, or, if none is specified, the size of
        each message in the mailbox.

        @type i: L{int} or L{None}
        @param i: The 0-based index of a message.

        @rtype: L{int} or L{list} of L{int}
        @return: The number of octets in the specified message, or, if an index
            is not specified, a list of the number of octets in each message in
            the mailbox.  Any value which corresponds to a deleted message is
            set to 0.

        @raise IndexError: When the index does not correspond to a message in
            the mailbox.
        """
        if i is None:
            return [self.listMessages(msg) for msg in range(len(self.msgs))]
        if i in self._delete:
            return 0
        return len(self.msgs[i])

    def getMessage(self, i: int) -> IO[bytes]:
        """
        Return an in-memory file-like object with the contents of a message.

        @param i: The 0-based index of a message.

        @return: An in-memory file-like object containing the message.

        @raise IndexError: When the index does not correspond to a message in
            the mailbox.
        """
        return io.BytesIO(self.msgs[i])

    def getUidl(self, i):
        """
        Get a unique identifier for a message.

        @type i: L{int}
        @param i: The 0-based index of a message.

        @rtype: L{bytes}
        @return: A hash of the contents of the message at the given index.

        @raise IndexError: When the index does not correspond to a message in
            the mailbox.
        """
        return md5(self.msgs[i]).hexdigest()

    def deleteMessage(self, i):
        """
        Mark a message for deletion.

        @type i: L{int}
        @param i: The 0-based index of a message to delete.

        @raise IndexError: When the index does not correspond to a message in
            the mailbox.
        """
        self._delete.add(i)

    def undeleteMessages(self):
        """
        Undelete any messages which have been marked for deletion.
        """
        self._delete = set()

    def sync(self):
        """
        Discard the contents of any messages marked for deletion.
        """
        for index in self._delete:
            self.msgs[index] = ""
        self._delete = set()


@implementer(portal.IRealm)
class MaildirDirdbmDomain(AbstractMaildirDomain):
    """
    A maildir-backed domain where membership is checked with a
    L{DirDBM <dirdbm.DirDBM>} database.

    The directory structure of a MaildirDirdbmDomain is:

    /passwd <-- a DirDBM directory

    /USER/{cur, new, del} <-- each user has these three directories

    @ivar postmaster: See L{__init__}.

    @type dbm: L{DirDBM <dirdbm.DirDBM>}
    @ivar dbm: The authentication database for the domain.
    """

    portal = None
    _credcheckers = None

    def __init__(self, service, root, postmaster=0):
        """
        @type service: L{MailService}
        @param service: An email service.

        @type root: L{bytes}
        @param root: The maildir root directory.

        @type postmaster: L{bool}
        @param postmaster: A flag indicating whether non-existent addresses
            should be forwarded to the postmaster (C{True}) or
            bounced (C{False}).
        """
        root = os.fsencode(root)
        AbstractMaildirDomain.__init__(self, service, root)
        dbm = os.path.join(root, b"passwd")
        if not os.path.exists(dbm):
            os.makedirs(dbm)
        self.dbm = dirdbm.open(dbm)
        self.postmaster = postmaster

    def userDirectory(self, name):
        """
        Return the path to a user's mail directory.

        @type name: L{bytes}
        @param name: A username.

        @rtype: L{bytes} or L{None}
        @return: The path to the user's mail directory for a valid user. For
            an invalid user, the path to the postmaster's mailbox if bounces
            are redirected there. Otherwise, L{None}.
        """
        if name not in self.dbm:
            if not self.postmaster:
                return None
            name = "postmaster"
        dir = os.path.join(self.root, name)
        if not os.path.exists(dir):
            initializeMaildir(dir)
        return dir

    def addUser(self, user, password):
        """
        Add a user to this domain by adding an entry in the authentication
        database and initializing the user's mail directory.

        @type user: L{bytes}
        @param user: A username.

        @type password: L{bytes}
        @param password: A password.
        """
        self.dbm[user] = password
        # Ensure it is initialized
        self.userDirectory(user)

    def getCredentialsCheckers(self):
        """
        Return credentials checkers for this domain.

        @rtype: L{list} of L{ICredentialsChecker
            <checkers.ICredentialsChecker>} provider
        @return: Credentials checkers for this domain.
        """
        if self._credcheckers is None:
            self._credcheckers = [DirdbmDatabase(self.dbm)]
        return self._credcheckers

    def requestAvatar(self, avatarId, mind, *interfaces):
        """
        Get the mailbox for an authenticated user.

        The mailbox for the authenticated user will be returned only if the
        given interfaces include L{IMailbox <pop3.IMailbox>}.  Requests for
        anonymous access will be met with a mailbox containing a message
        indicating that an internal error has occurred.

        @type avatarId: L{bytes} or C{twisted.cred.checkers.ANONYMOUS}
        @param avatarId: A string which identifies a user or an object which
            signals a request for anonymous access.

        @type mind: L{None}
        @param mind: Unused.

        @type interfaces: n-L{tuple} of C{zope.interface.Interface}
        @param interfaces: A group of interfaces, one of which the avatar
            must support.

        @rtype: 3-L{tuple} of (0) L{IMailbox <pop3.IMailbox>},
            (1) L{IMailbox <pop3.IMailbox>} provider, (2) no-argument
            callable
        @return: A tuple of the supported interface, a mailbox, and a
            logout function.

        @raise NotImplementedError: When the given interfaces do not include
            L{IMailbox <pop3.IMailbox>}.
        """
        if pop3.IMailbox not in interfaces:
            raise NotImplementedError("No interface")
        if avatarId == checkers.ANONYMOUS:
            mbox = StringListMailbox([INTERNAL_ERROR])
        else:
            mbox = MaildirMailbox(os.path.join(self.root, avatarId))

        return (pop3.IMailbox, mbox, lambda: None)


@implementer(checkers.ICredentialsChecker)
class DirdbmDatabase:
    """
    A credentials checker which authenticates users out of a
    L{DirDBM <dirdbm.DirDBM>} database.

    @type dirdbm: L{DirDBM <dirdbm.DirDBM>}
    @ivar dirdbm: An authentication database.
    """

    # credentialInterfaces is not used by the class
    credentialInterfaces = (
        credentials.IUsernamePassword,
        credentials.IUsernameHashedPassword,
    )

    def __init__(self, dbm):
        """
        @type dbm: L{DirDBM <dirdbm.DirDBM>}
        @param dbm: An authentication database.
        """
        self.dirdbm = dbm

    def requestAvatarId(self, c):
        """
        Authenticate a user and, if successful, return their username.

        @type c: L{IUsernamePassword <credentials.IUsernamePassword>} or
            L{IUsernameHashedPassword <credentials.IUsernameHashedPassword>}
            provider.
        @param c: Credentials.

        @rtype: L{bytes}
        @return: A string which identifies an user.

        @raise UnauthorizedLogin: When the credentials check fails.
        """
        if c.username in self.dirdbm:
            if c.checkPassword(self.dirdbm[c.username]):
                return c.username
        raise UnauthorizedLogin()
