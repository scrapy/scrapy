# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.mail.pop3} module.
"""


import base64
import hmac
import itertools
from collections import OrderedDict
from hashlib import md5
from io import BytesIO

from zope.interface import implementer
from zope.interface.verify import verifyClass

import twisted.cred.checkers
import twisted.cred.portal
import twisted.internet.protocol
import twisted.mail.pop3
import twisted.mail.protocols
from twisted import cred, internet, mail
from twisted.cred.credentials import IUsernameHashedPassword
from twisted.internet import defer
from twisted.mail import pop3
from twisted.protocols import loopback
from twisted.python import failure
from twisted.test.proto_helpers import LineSendingProtocol
from twisted.trial import unittest, util


class UtilityTests(unittest.SynchronousTestCase):
    """
    Test the various helper functions and classes used by the POP3 server
    protocol implementation.
    """

    def test_LineBuffering(self):
        """
        Test creating a LineBuffer and feeding it some lines.  The lines should
        build up in its internal buffer for a while and then get spat out to
        the writer.
        """
        output = []
        input = iter(itertools.cycle(["012", "345", "6", "7", "8", "9"]))
        c = pop3._IteratorBuffer(output.extend, input, 6)
        i = iter(c)
        self.assertEqual(output, [])  # Nothing is buffer
        next(i)
        self.assertEqual(output, [])  # '012' is buffered
        next(i)
        self.assertEqual(output, [])  # '012345' is buffered
        next(i)
        self.assertEqual(output, ["012", "345", "6"])  # Nothing is buffered
        for n in range(5):
            next(i)
        self.assertEqual(output, ["012", "345", "6", "7", "8", "9", "012", "345"])

    def test_FinishLineBuffering(self):
        """
        Test that a LineBuffer flushes everything when its iterator is
        exhausted, and itself raises StopIteration.
        """
        output = []
        input = iter(["a", "b", "c"])
        c = pop3._IteratorBuffer(output.extend, input, 5)
        for i in c:
            pass
        self.assertEqual(output, ["a", "b", "c"])

    def test_SuccessResponseFormatter(self):
        """
        Test that the thing that spits out POP3 'success responses' works
        right.
        """
        self.assertEqual(pop3.successResponse(b"Great."), b"+OK Great.\r\n")

    def test_StatLineFormatter(self):
        """
        Test that the function which formats stat lines does so appropriately.
        """
        statLine = list(pop3.formatStatResponse([]))[-1]
        self.assertEqual(statLine, b"+OK 0 0\r\n")

        statLine = list(pop3.formatStatResponse([10, 31, 0, 10101]))[-1]
        self.assertEqual(statLine, b"+OK 4 10142\r\n")

    def test_ListLineFormatter(self):
        """
        Test that the function which formats the lines in response to a LIST
        command does so appropriately.
        """
        listLines = list(pop3.formatListResponse([]))
        self.assertEqual(listLines, [b"+OK 0\r\n", b".\r\n"])

        listLines = list(pop3.formatListResponse([1, 2, 3, 100]))
        self.assertEqual(
            listLines,
            [b"+OK 4\r\n", b"1 1\r\n", b"2 2\r\n", b"3 3\r\n", b"4 100\r\n", b".\r\n"],
        )

    def test_UIDListLineFormatter(self):
        """
        Test that the function which formats lines in response to a UIDL
        command does so appropriately.
        """
        uids = ["abc", "def", "ghi"]
        listLines = list(pop3.formatUIDListResponse([], uids.__getitem__))
        self.assertEqual(listLines, [b"+OK \r\n", b".\r\n"])

        listLines = list(pop3.formatUIDListResponse([123, 431, 591], uids.__getitem__))
        self.assertEqual(
            listLines, [b"+OK \r\n", b"1 abc\r\n", b"2 def\r\n", b"3 ghi\r\n", b".\r\n"]
        )

        listLines = list(pop3.formatUIDListResponse([0, None, 591], uids.__getitem__))
        self.assertEqual(listLines, [b"+OK \r\n", b"1 abc\r\n", b"3 ghi\r\n", b".\r\n"])


class MyVirtualPOP3(mail.protocols.VirtualPOP3):
    """
    A virtual-domain-supporting POP3 server.
    """

    magic = b"<moshez>"

    def authenticateUserAPOP(self, user, digest):
        """
        Authenticate against a user against a virtual domain.

        @param user: The username.
        @param digest: The digested password.

        @return: A three-tuple like the one returned by
            L{IRealm.requestAvatar}.  The mailbox will be for the user given
            by C{user}.
        """
        user, domain = self.lookupDomain(user)
        return self.service.domains[b"baz.com"].authenticateUserAPOP(
            user, digest, self.magic, domain
        )


class DummyDomain:
    """
    A virtual domain for a POP3 server.
    """

    def __init__(self):
        self.users = {}

    def addUser(self, name):
        """
        Create a mailbox for a new user.

        @param name: The username.
        """
        self.users[name] = []

    def addMessage(self, name, message):
        """
        Add a message to the mailbox of the named user.

        @param name: The username.
        @param message: The contents of the message.
        """
        self.users[name].append(message)

    def authenticateUserAPOP(self, name, digest, magic, domain):
        """
        Succeed with a L{ListMailbox}.

        @param name: The name of the user authenticating.
        @param digest: ignored
        @param magic: ignored
        @param domain: ignored

        @return: A three-tuple like the one returned by
            L{IRealm.requestAvatar}.  The mailbox will be for the user given
            by C{name}.
        """
        return pop3.IMailbox, ListMailbox(self.users[name]), lambda: None


class ListMailbox:
    """
    A simple in-memory list implementation of L{IMailbox}.
    """

    def __init__(self, list):
        """
        @param list: The messages.
        """
        self.list = list

    def listMessages(self, i=None):
        """
        Get some message information.

        @param i: See L{pop3.IMailbox.listMessages}.
        @return: See L{pop3.IMailbox.listMessages}.
        """
        if i is None:
            return [len(l) for l in self.list]
        return len(self.list[i])

    def getMessage(self, i):
        """
        Get the message content.

        @param i: See L{pop3.IMailbox.getMessage}.
        @return: See L{pop3.IMailbox.getMessage}.
        """
        return BytesIO(self.list[i])

    def getUidl(self, i):
        """
        Construct a UID by using the given index value.

        @param i: See L{pop3.IMailbox.getUidl}.
        @return: See L{pop3.IMailbox.getUidl}.
        """
        return i

    def deleteMessage(self, i):
        """
        Wipe the message at the given index.

        @param i: See L{pop3.IMailbox.deleteMessage}.
        """
        self.list[i] = b""

    def sync(self):
        """
        No-op.

        @see: L{pop3.IMailbox.sync}
        """


class MyPOP3Downloader(pop3.POP3Client):
    """
    A POP3 client which downloads all messages from the server.
    """

    def handle_WELCOME(self, line):
        """
        Authenticate.

        @param line: The welcome response.
        """
        pop3.POP3Client.handle_WELCOME(self, line)
        self.apop(b"hello@baz.com", b"world")

    def handle_APOP(self, line):
        """
        Require an I{OK} response to I{APOP}.

        @param line: The I{APOP} response.
        """
        parts = line.split()
        code = parts[0]
        if code != b"+OK":
            raise AssertionError(f"code is: {code} , parts is: {parts} ")
        self.lines = []
        self.retr(1)

    def handle_RETR_continue(self, line):
        """
        Record one line of message information.

        @param line: A I{RETR} response line.
        """
        self.lines.append(line)

    def handle_RETR_end(self):
        """
        Record the received message information.
        """
        self.message = b"\n".join(self.lines) + b"\n"
        self.quit()

    def handle_QUIT(self, line):
        """
        Require an I{OK} response to I{QUIT}.

        @param line: The I{QUIT} response.
        """
        if line[:3] != b"+OK":
            raise AssertionError(b"code is " + line)


class POP3Tests(unittest.TestCase):
    """
    Tests for L{pop3.POP3}.
    """

    message = b"""\
Subject: urgent

Someone set up us the bomb!
"""

    expectedOutput = b"""\
+OK <moshez>\015
+OK Authentication succeeded\015
+OK \015
1 0\015
.\015
+OK %d\015
Subject: urgent\015
\015
Someone set up us the bomb!\015
.\015
+OK \015
""" % (
        len(message),
    )

    def setUp(self):
        """
        Set up a POP3 server with virtual domain support.
        """
        self.factory = internet.protocol.Factory()
        self.factory.domains = {}
        self.factory.domains[b"baz.com"] = DummyDomain()
        self.factory.domains[b"baz.com"].addUser(b"hello")
        self.factory.domains[b"baz.com"].addMessage(b"hello", self.message)

    def test_messages(self):
        """
        Messages can be downloaded over a loopback TCP connection.
        """
        client = LineSendingProtocol(
            [
                b"APOP hello@baz.com world",
                b"UIDL",
                b"RETR 1",
                b"QUIT",
            ]
        )
        server = MyVirtualPOP3()
        server.service = self.factory

        def check(ignored):
            output = b"\r\n".join(client.response) + b"\r\n"
            self.assertEqual(output, self.expectedOutput)

        return loopback.loopbackTCP(server, client).addCallback(check)

    def test_loopback(self):
        """
        Messages can be downloaded over a loopback connection.
        """
        protocol = MyVirtualPOP3()
        protocol.service = self.factory
        clientProtocol = MyPOP3Downloader()

        def check(ignored):
            self.assertEqual(clientProtocol.message, self.message)
            protocol.connectionLost(
                failure.Failure(Exception("Test harness disconnect"))
            )

        d = loopback.loopbackAsync(protocol, clientProtocol)
        return d.addCallback(check)

    test_loopback.suppress = [  # type: ignore[attr-defined]
        util.suppress(message="twisted.mail.pop3.POP3Client is deprecated")
    ]

    def test_incorrectDomain(self):
        """
        Look up a user in a domain which this server does not support.
        """
        factory = internet.protocol.Factory()
        factory.domains = {}
        factory.domains[b"twistedmatrix.com"] = DummyDomain()

        server = MyVirtualPOP3()
        server.service = factory
        exc = self.assertRaises(
            pop3.POP3Error, server.authenticateUserAPOP, b"nobody@baz.com", b"password"
        )
        self.assertEqual(exc.args[0], "no such domain baz.com")


class DummyPOP3(pop3.POP3):
    """
    A simple POP3 server with a hard-coded mailbox for any user.
    """

    magic = b"<moshez>"

    def authenticateUserAPOP(self, user, password):
        """
        Succeed with a L{DummyMailbox}.

        @param user: ignored
        @param password: ignored

        @return: A three-tuple like the one returned by
            L{IRealm.requestAvatar}.
        """
        return pop3.IMailbox, DummyMailbox(ValueError), lambda: None


class DummyPOP3Auth(DummyPOP3):
    """
    Class to test successful authentication in twisted.mail.pop3.POP3.
    """

    def __init__(self, user, password):
        self.portal = cred.portal.Portal(TestRealm())
        ch = cred.checkers.InMemoryUsernamePasswordDatabaseDontUse()
        ch.addUser(user, password)
        self.portal.registerChecker(ch)


class DummyMailbox(pop3.Mailbox):
    """
    An in-memory L{pop3.IMailbox} implementation.

    @ivar messages: A sequence of L{bytes} defining the messages in this
        mailbox.

    @ivar exceptionType: The type of exception to raise when an out-of-bounds
        index is addressed.
    """

    messages = [b"From: moshe\nTo: moshe\n\nHow are you, friend?\n"]

    def __init__(self, exceptionType):
        self.messages = DummyMailbox.messages[:]
        self.exceptionType = exceptionType

    def listMessages(self, i=None):
        """
        Get some message information.

        @param i: See L{pop3.IMailbox.listMessages}.
        @return: See L{pop3.IMailbox.listMessages}.
        """
        if i is None:
            return [len(m) for m in self.messages]
        if i >= len(self.messages):
            raise self.exceptionType()
        return len(self.messages[i])

    def getMessage(self, i):
        """
        Get the message content.

        @param i: See L{pop3.IMailbox.getMessage}.
        @return: See L{pop3.IMailbox.getMessage}.
        """
        return BytesIO(self.messages[i])

    def getUidl(self, i):
        """
        Construct a UID which is simply the string representation of the given
        index.

        @param i: See L{pop3.IMailbox.getUidl}.
        @return: See L{pop3.IMailbox.getUidl}.
        """
        if i >= len(self.messages):
            raise self.exceptionType()
        return b"%d" % (i,)

    def deleteMessage(self, i):
        """
        Wipe the message at the given index.

        @param i: See L{pop3.IMailbox.deleteMessage}.
        """
        self.messages[i] = b""


class AnotherPOP3Tests(unittest.TestCase):
    """
    Additional L{pop3.POP3} tests.
    """

    def runTest(self, lines, expectedOutput, protocolInstance=None):
        """
        Assert that when C{lines} are delivered to L{pop3.POP3} it responds
        with C{expectedOutput}.

        @param lines: A sequence of L{bytes} representing lines to deliver to
            the server.

        @param expectedOutput: A sequence of L{bytes} representing the
            expected response from the server.

        @param protocolInstance: Instance of L{twisted.mail.pop3.POP3} or
            L{None}. If L{None}, a new DummyPOP3 will be used.

        @return: A L{Deferred} that fires when the lines have been delivered
            and the output checked.
        """
        dummy = protocolInstance if protocolInstance else DummyPOP3()
        client = LineSendingProtocol(lines)
        d = loopback.loopbackAsync(dummy, client)
        return d.addCallback(self._cbRunTest, client, dummy, expectedOutput)

    def _cbRunTest(self, ignored, client, dummy, expectedOutput):
        self.assertEqual(b"\r\n".join(expectedOutput), b"\r\n".join(client.response))
        dummy.connectionLost(failure.Failure(Exception("Test harness disconnect")))
        return ignored

    def test_buffer(self):
        """
        Test a lot of different POP3 commands in an extremely pipelined
        scenario.

        This test may cover legitimate behavior, but the intent and
        granularity are not very good.  It would likely be an improvement to
        split it into a number of smaller, more focused tests.
        """
        return self.runTest(
            [
                b"APOP moshez dummy",
                b"LIST",
                b"UIDL",
                b"RETR 1",
                b"RETR 2",
                b"DELE 1",
                b"RETR 1",
                b"QUIT",
            ],
            [
                b"+OK <moshez>",
                b"+OK Authentication succeeded",
                b"+OK 1",
                b"1 44",
                b".",
                b"+OK ",
                b"1 0",
                b".",
                b"+OK 44",
                b"From: moshe",
                b"To: moshe",
                b"",
                b"How are you, friend?",
                b".",
                b"-ERR Bad message number argument",
                b"+OK ",
                b"-ERR message deleted",
                b"+OK ",
            ],
        )

    def test_noop(self):
        """
        Test the no-op command.
        """
        return self.runTest(
            [b"APOP spiv dummy", b"NOOP", b"QUIT"],
            [b"+OK <moshez>", b"+OK Authentication succeeded", b"+OK ", b"+OK "],
        )

    def test_badUTF8CharactersInCommand(self):
        """
        Sending a command with invalid UTF-8 characters
        will raise a L{pop3.POP3Error}.
        """
        error = b"not authenticated yet: cannot do \x81PASS"
        d = self.runTest(
            [b"\x81PASS", b"QUIT"],
            [
                b"+OK <moshez>",
                b"-ERR bad protocol or server: POP3Error: " + error,
                b"+OK ",
            ],
        )
        errors = self.flushLoggedErrors(pop3.POP3Error)
        self.assertEqual(len(errors), 1)
        return d

    def test_authListing(self):
        """
        L{pop3.POP3} responds to an I{AUTH} command with a list of supported
        authentication types based on its factory's C{challengers}.
        """
        p = DummyPOP3()
        p.factory = internet.protocol.Factory()
        p.factory.challengers = {b"Auth1": None, b"secondAuth": None, b"authLast": None}
        client = LineSendingProtocol(
            [
                b"AUTH",
                b"QUIT",
            ]
        )

        d = loopback.loopbackAsync(p, client)
        return d.addCallback(self._cbTestAuthListing, client)

    def _cbTestAuthListing(self, ignored, client):
        self.assertTrue(client.response[1].startswith(b"+OK"))
        self.assertEqual(
            sorted(client.response[2:5]), [b"AUTH1", b"AUTHLAST", b"SECONDAUTH"]
        )
        self.assertEqual(client.response[5], b".")

    def run_PASS(
        self,
        real_user,
        real_password,
        tried_user=None,
        tried_password=None,
        after_auth_input=[],
        after_auth_output=[],
    ):
        """
        Test a login with PASS.

        If L{real_user} matches L{tried_user} and L{real_password} matches
        L{tried_password}, a successful login will be expected.
        Otherwise an unsuccessful login will be expected.

        @type real_user: L{bytes}
        @param real_user: The user to test.

        @type real_password: L{bytes}
        @param real_password: The password of the test user.

        @type tried_user: L{bytes} or L{None}
        @param tried_user: The user to call USER with.
            If None, real_user will be used.

        @type tried_password: L{bytes} or L{None}
        @param tried_password: The password to call PASS with.
            If None, real_password will be used.

        @type after_auth_input: L{list} of l{bytes}
        @param after_auth_input: Extra protocol input after authentication.

        @type after_auth_output: L{list} of l{bytes}
        @param after_auth_output: Extra protocol output after authentication.
        """
        if not tried_user:
            tried_user = real_user
        if not tried_password:
            tried_password = real_password
        response = [
            b"+OK <moshez>",
            b"+OK USER accepted, send PASS",
            b"-ERR Authentication failed",
        ]
        if real_user == tried_user and real_password == tried_password:
            response = [
                b"+OK <moshez>",
                b"+OK USER accepted, send PASS",
                b"+OK Authentication succeeded",
            ]
        fullInput = [
            b" ".join([b"USER", tried_user]),
            b" ".join([b"PASS", tried_password]),
        ]

        fullInput += after_auth_input + [b"QUIT"]
        response += after_auth_output + [b"+OK "]

        return self.runTest(
            fullInput,
            response,
            protocolInstance=DummyPOP3Auth(real_user, real_password),
        )

    def run_PASS_before_USER(self, password):
        """
        Test protocol violation produced by calling PASS before USER.
        @type password: L{bytes}
        @param password: A password to test.
        """
        return self.runTest(
            [b" ".join([b"PASS", password]), b"QUIT"],
            [b"+OK <moshez>", b"-ERR USER required before PASS", b"+OK "],
        )

    def test_illegal_PASS_before_USER(self):
        """
        Test PASS before USER with a wrong password.
        """
        return self.run_PASS_before_USER(b"fooz")

    def test_empty_PASS_before_USER(self):
        """
        Test PASS before USER with an empty password.
        """
        return self.run_PASS_before_USER(b"")

    def test_one_space_PASS_before_USER(self):
        """
        Test PASS before USER with an password that is a space.
        """
        return self.run_PASS_before_USER(b" ")

    def test_space_PASS_before_USER(self):
        """
        Test PASS before USER with a password containing a space.
        """
        return self.run_PASS_before_USER(b"fooz barz")

    def test_multiple_spaces_PASS_before_USER(self):
        """
        Test PASS before USER with a password containing multiple spaces.
        """
        return self.run_PASS_before_USER(b"fooz barz asdf")

    def test_other_whitespace_PASS_before_USER(self):
        """
        Test PASS before USER with a password containing tabs and spaces.
        """
        return self.run_PASS_before_USER(b"fooz barz\tcrazy@! \t ")

    def test_good_PASS(self):
        """
        Test PASS with a good password.
        """
        return self.run_PASS(b"testuser", b"fooz")

    def test_space_PASS(self):
        """
        Test PASS with a password containing a space.
        """
        return self.run_PASS(b"testuser", b"fooz barz")

    def test_multiple_spaces_PASS(self):
        """
        Test PASS with a password containing a space.
        """
        return self.run_PASS(b"testuser", b"fooz barz asdf")

    def test_other_whitespace_PASS(self):
        """
        Test PASS with a password containing tabs and spaces.
        """
        return self.run_PASS(b"testuser", b"fooz barz\tcrazy@! \t ")

    def test_pass_wrong_user(self):
        """
        Test PASS with a wrong user.
        """
        return self.run_PASS(b"testuser", b"fooz", tried_user=b"wronguser")

    def test_wrong_PASS(self):
        """
        Test PASS with a wrong password.
        """
        return self.run_PASS(b"testuser", b"fooz", tried_password=b"barz")

    def test_wrong_space_PASS(self):
        """
        Test PASS with a password containing a space.
        """
        return self.run_PASS(b"testuser", b"fooz barz", tried_password=b"foozbarz ")

    def test_wrong_multiple_spaces_PASS(self):
        """
        Test PASS with a password containing a space.
        """
        return self.run_PASS(
            b"testuser", b"fooz barz asdf", tried_password=b"foozbarz   "
        )

    def test_wrong_other_whitespace_PASS(self):
        """
        Test PASS with a password containing tabs and spaces.
        """
        return self.run_PASS(b"testuser", b"fooz barz\tcrazy@! \t ")

    def test_wrong_command(self):
        """
        After logging in, test a dummy command that is not defined.
        """
        extra_input = [b"DUMMY COMMAND"]
        extra_output = [
            b" ".join(
                [
                    b"-ERR bad protocol or server: POP3Error:",
                    b"Unknown protocol command: DUMMY",
                ]
            )
        ]

        return self.run_PASS(
            b"testuser",
            b"testpassword",
            after_auth_input=extra_input,
            after_auth_output=extra_output,
        ).addCallback(self.flushLoggedErrors, pop3.POP3Error)


@implementer(pop3.IServerFactory)
class TestServerFactory:
    """
    A L{pop3.IServerFactory} implementation, for use by the test suite, with
    some behavior controlled by the values of (settable) public attributes and
    other behavior based on values hard-coded both here and in some test
    methods.
    """

    def cap_IMPLEMENTATION(self):
        """
        Return the hard-coded value.

        @return: L{pop3.IServerFactory}
        """
        return "Test Implementation String"

    def cap_EXPIRE(self):
        """
        Return the hard-coded value.

        @return: L{pop3.IServerFactory}
        """
        return 60

    challengers = OrderedDict([(b"SCHEME_1", None), (b"SCHEME_2", None)])

    def cap_LOGIN_DELAY(self):
        """
        Return the hard-coded value.

        @return: L{pop3.IServerFactory}
        """
        return 120

    pue = True

    def perUserExpiration(self):
        """
        Return the hard-coded value.

        @return: L{pop3.IServerFactory}
        """
        return self.pue

    puld = True

    def perUserLoginDelay(self):
        """
        Return the hard-coded value.

        @return: L{pop3.IServerFactory}
        """
        return self.puld


class TestMailbox:
    """
    An incomplete L{IMailbox} implementation with certain per-user values
    hard-coded and known by tests in this module.


    This is useful for testing the server's per-user capability
    implementation.
    """

    loginDelay = 100
    messageExpiration = 25


def contained(testcase, s, *caps):
    """
    Assert that the given capability is included in all of the capability
    sets.

    @param testcase: A L{unittest.TestCase} to use to make assertions.

    @param s: The capability for which to check.
    @type s: L{bytes}

    @param caps: The capability sets in which to check.
    @type caps: L{tuple} of iterable
    """
    for c in caps:
        testcase.assertIn(s, c)


class CapabilityTests(unittest.TestCase):
    """
    Tests for L{pop3.POP3}'s per-user capability handling.
    """

    def setUp(self):
        """
        Create a POP3 server with some capabilities.
        """
        s = BytesIO()
        p = pop3.POP3()
        p.factory = TestServerFactory()
        p.transport = internet.protocol.FileWrapper(s)
        p.connectionMade()
        p.do_CAPA()

        self.caps = p.listCapabilities()
        self.pcaps = s.getvalue().splitlines()

        s = BytesIO()
        p.mbox = TestMailbox()
        p.transport = internet.protocol.FileWrapper(s)
        p.do_CAPA()

        self.lpcaps = s.getvalue().splitlines()
        p.connectionLost(failure.Failure(Exception("Test harness disconnect")))

    def test_UIDL(self):
        """
        The server can advertise the I{UIDL} capability.
        """
        contained(self, b"UIDL", self.caps, self.pcaps, self.lpcaps)

    def test_TOP(self):
        """
        The server can advertise the I{TOP} capability.
        """
        contained(self, b"TOP", self.caps, self.pcaps, self.lpcaps)

    def test_USER(self):
        """
        The server can advertise the I{USER} capability.
        """
        contained(self, b"USER", self.caps, self.pcaps, self.lpcaps)

    def test_EXPIRE(self):
        """
        The server can advertise its per-user expiration as well as a global
        expiration.
        """
        contained(self, b"EXPIRE 60 USER", self.caps, self.pcaps)
        contained(self, b"EXPIRE 25", self.lpcaps)

    def test_IMPLEMENTATION(self):
        """
        The server can advertise its implementation string.
        """
        contained(
            self,
            b"IMPLEMENTATION Test Implementation String",
            self.caps,
            self.pcaps,
            self.lpcaps,
        )

    def test_SASL(self):
        """
        The server can advertise the SASL schemes it supports.
        """
        contained(self, b"SASL SCHEME_1 SCHEME_2", self.caps, self.pcaps, self.lpcaps)

    def test_LOGIN_DELAY(self):
        """
        The can advertise a per-user login delay as well as a global login
        delay.
        """
        contained(self, b"LOGIN-DELAY 120 USER", self.caps, self.pcaps)
        self.assertIn(b"LOGIN-DELAY 100", self.lpcaps)


class GlobalCapabilitiesTests(unittest.TestCase):
    """
    Tests for L{pop3.POP3}'s global capability handling.
    """

    def setUp(self):
        """
        Create a POP3 server with some capabilities.
        """
        s = BytesIO()
        p = pop3.POP3()
        p.factory = TestServerFactory()
        p.factory.pue = p.factory.puld = False
        p.transport = internet.protocol.FileWrapper(s)
        p.connectionMade()
        p.do_CAPA()

        self.caps = p.listCapabilities()
        self.pcaps = s.getvalue().splitlines()

        s = BytesIO()
        p.mbox = TestMailbox()
        p.transport = internet.protocol.FileWrapper(s)
        p.do_CAPA()

        self.lpcaps = s.getvalue().splitlines()
        p.connectionLost(failure.Failure(Exception("Test harness disconnect")))

    def test_EXPIRE(self):
        """
        I{EXPIRE} is in the server's advertised capabilities.
        """
        contained(self, b"EXPIRE 60", self.caps, self.pcaps, self.lpcaps)

    def test_LOGIN_DELAY(self):
        """
        I{LOGIN-DELAY} is in the server's advertised capabilities.
        """
        contained(self, b"LOGIN-DELAY 120", self.caps, self.pcaps, self.lpcaps)


class TestRealm:
    """
    An L{IRealm} which knows about a single test account's mailbox.
    """

    def requestAvatar(self, avatarId, mind, *interfaces):
        """
        Retrieve a mailbox for I{testuser} or fail.

        @param avatarId: See L{IRealm.requestAvatar}.
        @param mind: See L{IRealm.requestAvatar}.
        @param interfaces: See L{IRealm.requestAvatar}.

        @raises: L{AssertionError} when requesting an C{avatarId} other than
            I{testuser}.
        """
        if avatarId == b"testuser":
            return pop3.IMailbox, DummyMailbox(ValueError), lambda: None
        assert False


class SASLTests(unittest.TestCase):
    """
    Tests for L{pop3.POP3}'s SASL implementation.
    """

    def test_ValidLogin(self):
        """
        A CRAM-MD5-based SASL login attempt succeeds if it uses a username and
        a hashed password known to the server's credentials checker.
        """
        p = pop3.POP3()
        p.factory = TestServerFactory()
        p.factory.challengers = {b"CRAM-MD5": cred.credentials.CramMD5Credentials}
        p.portal = cred.portal.Portal(TestRealm())
        ch = cred.checkers.InMemoryUsernamePasswordDatabaseDontUse()
        ch.addUser(b"testuser", b"testpassword")
        p.portal.registerChecker(ch)

        s = BytesIO()
        p.transport = internet.protocol.FileWrapper(s)
        p.connectionMade()

        p.lineReceived(b"CAPA")
        self.assertTrue(s.getvalue().find(b"SASL CRAM-MD5") >= 0)

        p.lineReceived(b"AUTH CRAM-MD5")
        chal = s.getvalue().splitlines()[-1][2:]
        chal = base64.b64decode(chal)
        response = (
            hmac.HMAC(b"testpassword", chal, digestmod=md5).hexdigest().encode("ascii")
        )

        p.lineReceived(base64.b64encode(b"testuser " + response))
        self.assertTrue(p.mbox)
        self.assertTrue(s.getvalue().splitlines()[-1].find(b"+OK") >= 0)
        p.connectionLost(failure.Failure(Exception("Test harness disconnect")))


class CommandMixin:
    """
    Tests for all the commands a POP3 server is allowed to receive.
    """

    extraMessage = b"""\
From: guy
To: fellow

More message text for you.
"""

    def setUp(self):
        """
        Make a POP3 server protocol instance hooked up to a simple mailbox and
        a transport that buffers output to a BytesIO.
        """
        p = pop3.POP3()
        p.mbox = self.mailboxType(self.exceptionType)
        p.schedule = list
        self.pop3Server = p

        s = BytesIO()
        p.transport = internet.protocol.FileWrapper(s)
        p.connectionMade()
        s.seek(0)
        s.truncate(0)
        self.pop3Transport = s

    def tearDown(self):
        """
        Disconnect the server protocol so it can clean up anything it might
        need to clean up.
        """
        self.pop3Server.connectionLost(
            failure.Failure(Exception("Test harness disconnect"))
        )

    def _flush(self):
        """
        Do some of the things that the reactor would take care of, if the
        reactor were actually running.
        """
        # Oh man FileWrapper is pooh.
        self.pop3Server.transport._checkProducer()

    def test_LIST(self):
        """
        Test the two forms of list: with a message index number, which should
        return a short-form response, and without a message index number, which
        should return a long-form response, one line per message.
        """
        p = self.pop3Server
        s = self.pop3Transport

        p.lineReceived(b"LIST 1")
        self._flush()
        self.assertEqual(s.getvalue(), b"+OK 1 44\r\n")
        s.seek(0)
        s.truncate(0)

        p.lineReceived(b"LIST")
        self._flush()
        self.assertEqual(s.getvalue(), b"+OK 1\r\n1 44\r\n.\r\n")

    def test_LISTWithBadArgument(self):
        """
        Test that non-integers and out-of-bound integers produce appropriate
        error responses.
        """
        p = self.pop3Server
        s = self.pop3Transport

        p.lineReceived(b"LIST a")
        self.assertEqual(s.getvalue(), b"-ERR Invalid message-number: a\r\n")
        s.seek(0)
        s.truncate(0)

        p.lineReceived(b"LIST 0")
        self.assertEqual(s.getvalue(), b"-ERR Invalid message-number: 0\r\n")
        s.seek(0)
        s.truncate(0)

        p.lineReceived(b"LIST 2")
        self.assertEqual(s.getvalue(), b"-ERR Invalid message-number: 2\r\n")
        s.seek(0)
        s.truncate(0)

    def test_UIDL(self):
        """
        Test the two forms of the UIDL command.  These are just like the two
        forms of the LIST command.
        """
        p = self.pop3Server
        s = self.pop3Transport

        p.lineReceived(b"UIDL 1")
        self.assertEqual(s.getvalue(), b"+OK 0\r\n")
        s.seek(0)
        s.truncate(0)

        p.lineReceived(b"UIDL")
        self._flush()
        self.assertEqual(s.getvalue(), b"+OK \r\n1 0\r\n.\r\n")

    def test_UIDLWithBadArgument(self):
        """
        Test that UIDL with a non-integer or an out-of-bounds integer produces
        the appropriate error response.
        """
        p = self.pop3Server
        s = self.pop3Transport

        p.lineReceived(b"UIDL a")
        self.assertEqual(s.getvalue(), b"-ERR Bad message number argument\r\n")
        s.seek(0)
        s.truncate(0)

        p.lineReceived(b"UIDL 0")
        self.assertEqual(s.getvalue(), b"-ERR Bad message number argument\r\n")
        s.seek(0)
        s.truncate(0)

        p.lineReceived(b"UIDL 2")
        self.assertEqual(s.getvalue(), b"-ERR Bad message number argument\r\n")
        s.seek(0)
        s.truncate(0)

    def test_STAT(self):
        """
        Test the single form of the STAT command, which returns a short-form
        response of the number of messages in the mailbox and their total size.
        """
        p = self.pop3Server
        s = self.pop3Transport

        p.lineReceived(b"STAT")
        self._flush()
        self.assertEqual(s.getvalue(), b"+OK 1 44\r\n")

    def test_RETR(self):
        """
        Test downloading a message.
        """
        p = self.pop3Server
        s = self.pop3Transport

        p.lineReceived(b"RETR 1")
        self._flush()
        self.assertEqual(
            s.getvalue(),
            b"+OK 44\r\n"
            b"From: moshe\r\n"
            b"To: moshe\r\n"
            b"\r\n"
            b"How are you, friend?\r\n"
            b".\r\n",
        )
        s.seek(0)
        s.truncate(0)

    def test_RETRWithBadArgument(self):
        """
        Test that trying to download a message with a bad argument, either not
        an integer or an out-of-bounds integer, fails with the appropriate
        error response.
        """
        p = self.pop3Server
        s = self.pop3Transport

        p.lineReceived(b"RETR a")
        self.assertEqual(s.getvalue(), b"-ERR Bad message number argument\r\n")
        s.seek(0)
        s.truncate(0)

        p.lineReceived(b"RETR 0")
        self.assertEqual(s.getvalue(), b"-ERR Bad message number argument\r\n")
        s.seek(0)
        s.truncate(0)

        p.lineReceived(b"RETR 2")
        self.assertEqual(s.getvalue(), b"-ERR Bad message number argument\r\n")
        s.seek(0)
        s.truncate(0)

    def test_TOP(self):
        """
        Test downloading the headers and part of the body of a message.
        """
        p = self.pop3Server
        s = self.pop3Transport
        p.mbox.messages.append(self.extraMessage)

        p.lineReceived(b"TOP 1 0")
        self._flush()
        self.assertEqual(
            s.getvalue(),
            b"+OK Top of message follows\r\n"
            b"From: moshe\r\n"
            b"To: moshe\r\n"
            b"\r\n"
            b".\r\n",
        )

    def test_TOPWithBadArgument(self):
        """
        Test that trying to download a message with a bad argument, either a
        message number which isn't an integer or is an out-of-bounds integer or
        a number of lines which isn't an integer or is a negative integer,
        fails with the appropriate error response.
        """
        p = self.pop3Server
        s = self.pop3Transport
        p.mbox.messages.append(self.extraMessage)

        p.lineReceived(b"TOP 1 a")
        self.assertEqual(s.getvalue(), b"-ERR Bad line count argument\r\n")
        s.seek(0)
        s.truncate(0)

        p.lineReceived(b"TOP 1 -1")
        self.assertEqual(s.getvalue(), b"-ERR Bad line count argument\r\n")
        s.seek(0)
        s.truncate(0)

        p.lineReceived(b"TOP a 1")
        self.assertEqual(s.getvalue(), b"-ERR Bad message number argument\r\n")
        s.seek(0)
        s.truncate(0)

        p.lineReceived(b"TOP 0 1")
        self.assertEqual(s.getvalue(), b"-ERR Bad message number argument\r\n")
        s.seek(0)
        s.truncate(0)

        p.lineReceived(b"TOP 3 1")
        self.assertEqual(s.getvalue(), b"-ERR Bad message number argument\r\n")
        s.seek(0)
        s.truncate(0)

    def test_LAST(self):
        """
        Test the exceedingly pointless LAST command, which tells you the
        highest message index which you have already downloaded.
        """
        p = self.pop3Server
        s = self.pop3Transport
        p.mbox.messages.append(self.extraMessage)

        p.lineReceived(b"LAST")
        self.assertEqual(s.getvalue(), b"+OK 0\r\n")
        s.seek(0)
        s.truncate(0)

    def test_RetrieveUpdatesHighest(self):
        """
        Test that issuing a RETR command updates the LAST response.
        """
        p = self.pop3Server
        s = self.pop3Transport
        p.mbox.messages.append(self.extraMessage)

        p.lineReceived(b"RETR 2")
        self._flush()
        s.seek(0)
        s.truncate(0)
        p.lineReceived(b"LAST")
        self.assertEqual(s.getvalue(), b"+OK 2\r\n")
        s.seek(0)
        s.truncate(0)

    def test_TopUpdatesHighest(self):
        """
        Test that issuing a TOP command updates the LAST response.
        """
        p = self.pop3Server
        s = self.pop3Transport
        p.mbox.messages.append(self.extraMessage)

        p.lineReceived(b"TOP 2 10")
        self._flush()
        s.seek(0)
        s.truncate(0)
        p.lineReceived(b"LAST")
        self.assertEqual(s.getvalue(), b"+OK 2\r\n")

    def test_HighestOnlyProgresses(self):
        """
        Test that downloading a message with a smaller index than the current
        LAST response doesn't change the LAST response.
        """
        p = self.pop3Server
        s = self.pop3Transport
        p.mbox.messages.append(self.extraMessage)

        p.lineReceived(b"RETR 2")
        self._flush()
        p.lineReceived(b"TOP 1 10")
        self._flush()
        s.seek(0)
        s.truncate(0)
        p.lineReceived(b"LAST")
        self.assertEqual(s.getvalue(), b"+OK 2\r\n")

    def test_ResetClearsHighest(self):
        """
        Test that issuing RSET changes the LAST response to 0.
        """
        p = self.pop3Server
        s = self.pop3Transport
        p.mbox.messages.append(self.extraMessage)

        p.lineReceived(b"RETR 2")
        self._flush()
        p.lineReceived(b"RSET")
        s.seek(0)
        s.truncate(0)
        p.lineReceived(b"LAST")
        self.assertEqual(s.getvalue(), b"+OK 0\r\n")


_listMessageDeprecation = (
    "twisted.mail.pop3.IMailbox.listMessages may not "
    "raise IndexError for out-of-bounds message numbers: "
    "raise ValueError instead."
)
_listMessageSuppression = util.suppress(
    message=_listMessageDeprecation, category=PendingDeprecationWarning
)

_getUidlDeprecation = (
    "twisted.mail.pop3.IMailbox.getUidl may not "
    "raise IndexError for out-of-bounds message numbers: "
    "raise ValueError instead."
)
_getUidlSuppression = util.suppress(
    message=_getUidlDeprecation, category=PendingDeprecationWarning
)


class IndexErrorCommandTests(CommandMixin, unittest.TestCase):
    """
    Run all of the command tests against a mailbox which raises IndexError
    when an out of bounds request is made.  This behavior will be deprecated
    shortly and then removed.
    """

    exceptionType = IndexError
    mailboxType = DummyMailbox

    def test_LISTWithBadArgument(self):
        """
        An attempt to get metadata about a message with a bad argument fails
        with an I{ERR} response even if the mailbox implementation raises
        L{IndexError}.
        """
        return CommandMixin.test_LISTWithBadArgument(self)

    test_LISTWithBadArgument.suppress = [_listMessageSuppression]  # type: ignore[attr-defined]

    def test_UIDLWithBadArgument(self):
        """
        An attempt to look up the UID of a message with a bad argument fails
        with an I{ERR} response even if the mailbox implementation raises
        L{IndexError}.
        """
        return CommandMixin.test_UIDLWithBadArgument(self)

    test_UIDLWithBadArgument.suppress = [_getUidlSuppression]  # type: ignore[attr-defined]

    def test_TOPWithBadArgument(self):
        """
        An attempt to download some of a message with a bad argument fails with
        an I{ERR} response even if the mailbox implementation raises
        L{IndexError}.
        """
        return CommandMixin.test_TOPWithBadArgument(self)

    test_TOPWithBadArgument.suppress = [_listMessageSuppression]  # type: ignore[attr-defined]

    def test_RETRWithBadArgument(self):
        """
        An attempt to download a message with a bad argument fails with an
        I{ERR} response even if the mailbox implementation raises
        L{IndexError}.
        """
        return CommandMixin.test_RETRWithBadArgument(self)

    test_RETRWithBadArgument.suppress = [_listMessageSuppression]  # type: ignore[attr-defined]


class ValueErrorCommandTests(CommandMixin, unittest.TestCase):
    """
    Run all of the command tests against a mailbox which raises ValueError
    when an out of bounds request is made.  This is the correct behavior and
    after support for mailboxes which raise IndexError is removed, this will
    become just C{CommandTestCase}.
    """

    exceptionType = ValueError
    mailboxType = DummyMailbox


class SyncDeferredMailbox(DummyMailbox):
    """
    Mailbox which has a listMessages implementation which returns a Deferred
    which has already fired.
    """

    def listMessages(self, n=None):
        """
        Synchronously list messages.

        @type n: L{int} or L{None}
        @param n: The 0-based index of the message.

        @return: A L{Deferred} which already has a message list result.
        """
        return defer.succeed(DummyMailbox.listMessages(self, n))


class IndexErrorSyncDeferredCommandTests(IndexErrorCommandTests):
    """
    Run all of the L{IndexErrorCommandTests} tests with a
    synchronous-Deferred returning IMailbox implementation.
    """

    mailboxType = SyncDeferredMailbox


class ValueErrorSyncDeferredCommandTests(ValueErrorCommandTests):
    """
    Run all of the L{ValueErrorCommandTests} tests with a
    synchronous-Deferred returning IMailbox implementation.
    """

    mailboxType = SyncDeferredMailbox


class AsyncDeferredMailbox(DummyMailbox):
    """
    Mailbox which has a listMessages implementation which returns a Deferred
    which has not yet fired.
    """

    def __init__(self, *a, **kw):
        self.waiting = []
        DummyMailbox.__init__(self, *a, **kw)

    def listMessages(self, n=None):
        """
        Record a new unfired L{Deferred} in C{self.waiting} and return it.

        @type n: L{int} or L{None}
        @param n: The 0-based index of the message.

        @return: The L{Deferred}
        """
        d = defer.Deferred()
        # See AsyncDeferredMailbox._flush
        self.waiting.append((d, DummyMailbox.listMessages(self, n)))
        return d


class IndexErrorAsyncDeferredCommandTests(IndexErrorCommandTests):
    """
    Run all of the L{IndexErrorCommandTests} tests with an
    asynchronous-Deferred returning IMailbox implementation.
    """

    mailboxType = AsyncDeferredMailbox

    def _flush(self):
        """
        Fire whatever Deferreds we've built up in our mailbox.
        """
        while self.pop3Server.mbox.waiting:
            d, a = self.pop3Server.mbox.waiting.pop()
            d.callback(a)
        IndexErrorCommandTests._flush(self)


class ValueErrorAsyncDeferredCommandTests(ValueErrorCommandTests):
    """
    Run all of the L{IndexErrorCommandTests} tests with an
    asynchronous-Deferred returning IMailbox implementation.
    """

    mailboxType = AsyncDeferredMailbox

    def _flush(self):
        """
        Fire whatever Deferreds we've built up in our mailbox.
        """
        while self.pop3Server.mbox.waiting:
            d, a = self.pop3Server.mbox.waiting.pop()
            d.callback(a)
        ValueErrorCommandTests._flush(self)


class POP3MiscTests(unittest.SynchronousTestCase):
    """
    Miscellaneous tests more to do with module/package structure than
    anything to do with the Post Office Protocol.
    """

    def test_all(self):
        """
        This test checks that all names listed in
        twisted.mail.pop3.__all__ are actually present in the module.
        """
        mod = twisted.mail.pop3
        for attr in mod.__all__:
            self.assertTrue(hasattr(mod, attr))


class POP3ClientDeprecationTests(unittest.SynchronousTestCase):
    """
    Tests for the now deprecated L{twisted.mail.pop3client} module.
    """

    def test_deprecation(self):
        """
        A deprecation warning is emitted when directly importing the now
        deprected pop3client module.

        This test might fail is some other code has already imported it.
        No code should use the deprected module.
        """
        from twisted.mail import pop3client

        warningsShown = self.flushWarnings(offendingFunctions=[self.test_deprecation])
        self.assertEqual(warningsShown[0]["category"], DeprecationWarning)
        self.assertEqual(
            warningsShown[0]["message"],
            "twisted.mail.pop3client was deprecated in Twisted 21.2.0. "
            "Use twisted.mail.pop3 instead.",
        )
        self.assertEqual(len(warningsShown), 1)
        pop3client  # Fake usage to please pyflakes.


class APOPCredentialsTests(unittest.SynchronousTestCase):
    def test_implementsIUsernamePassword(self):
        """
        L{APOPCredentials} implements
        L{twisted.cred.credentials.IUsernameHashedPassword}.
        """
        self.assertTrue(verifyClass(IUsernameHashedPassword, pop3.APOPCredentials))
