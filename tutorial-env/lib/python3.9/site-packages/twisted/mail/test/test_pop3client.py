# -*- test-case-name: twisted.mail.test.test_pop3client -*-
# Copyright (c) 2001-2004 Divmod Inc.
# See LICENSE for details.

import inspect
import sys
from typing import List
from unittest import skipIf

from zope.interface import directlyProvides

import twisted.mail._pop3client
from twisted.internet import defer, error, interfaces, protocol, reactor
from twisted.mail.pop3 import (
    AdvancedPOP3Client as POP3Client,
    InsecureAuthenticationDisallowed,
    ServerErrorResponse,
)
from twisted.mail.test import pop3testserver
from twisted.protocols import basic, loopback
from twisted.python import log
from twisted.test.proto_helpers import StringTransport
from twisted.trial.unittest import TestCase

try:
    from twisted.test.ssl_helpers import ClientTLSContext, ServerTLSContext
except ImportError:
    ClientTLSContext = None  # type: ignore[assignment,misc]
    ServerTLSContext = None  # type: ignore[assignment,misc]


class StringTransportWithConnectionLosing(StringTransport):
    def loseConnection(self):
        self.protocol.connectionLost(error.ConnectionDone())


capCache = {
    b"TOP": None,
    b"LOGIN-DELAY": b"180",
    b"UIDL": None,
    b"STLS": None,
    b"USER": None,
    b"SASL": b"LOGIN",
}


def setUp(greet=True):
    p = POP3Client()

    # Skip the CAPA login will issue if it doesn't already have a
    # capability cache
    p._capCache = capCache

    t = StringTransportWithConnectionLosing()
    t.protocol = p
    p.makeConnection(t)

    if greet:
        p.dataReceived(b"+OK Hello!\r\n")

    return p, t


def strip(f):
    return lambda result, f=f: f()


class POP3ClientLoginTests(TestCase):
    def testNegativeGreeting(self):
        p, t = setUp(greet=False)
        p.allowInsecureLogin = True
        d = p.login(b"username", b"password")
        p.dataReceived(b"-ERR Offline for maintenance\r\n")
        return self.assertFailure(d, ServerErrorResponse).addCallback(
            lambda exc: self.assertEqual(exc.args[0], b"Offline for maintenance")
        )

    def testOkUser(self):
        p, t = setUp()
        d = p.user(b"username")
        self.assertEqual(t.value(), b"USER username\r\n")
        p.dataReceived(b"+OK send password\r\n")
        return d.addCallback(self.assertEqual, b"send password")

    def testBadUser(self):
        p, t = setUp()
        d = p.user(b"username")
        self.assertEqual(t.value(), b"USER username\r\n")
        p.dataReceived(b"-ERR account suspended\r\n")
        return self.assertFailure(d, ServerErrorResponse).addCallback(
            lambda exc: self.assertEqual(exc.args[0], b"account suspended")
        )

    def testOkPass(self):
        p, t = setUp()
        d = p.password(b"password")
        self.assertEqual(t.value(), b"PASS password\r\n")
        p.dataReceived(b"+OK you're in!\r\n")
        return d.addCallback(self.assertEqual, b"you're in!")

    def testBadPass(self):
        p, t = setUp()
        d = p.password(b"password")
        self.assertEqual(t.value(), b"PASS password\r\n")
        p.dataReceived(b"-ERR go away\r\n")
        return self.assertFailure(d, ServerErrorResponse).addCallback(
            lambda exc: self.assertEqual(exc.args[0], b"go away")
        )

    def testOkLogin(self):
        p, t = setUp()
        p.allowInsecureLogin = True
        d = p.login(b"username", b"password")
        self.assertEqual(t.value(), b"USER username\r\n")
        p.dataReceived(b"+OK go ahead\r\n")
        self.assertEqual(t.value(), b"USER username\r\nPASS password\r\n")
        p.dataReceived(b"+OK password accepted\r\n")
        return d.addCallback(self.assertEqual, b"password accepted")

    def testBadPasswordLogin(self):
        p, t = setUp()
        p.allowInsecureLogin = True
        d = p.login(b"username", b"password")
        self.assertEqual(t.value(), b"USER username\r\n")
        p.dataReceived(b"+OK waiting on you\r\n")
        self.assertEqual(t.value(), b"USER username\r\nPASS password\r\n")
        p.dataReceived(b"-ERR bogus login\r\n")
        return self.assertFailure(d, ServerErrorResponse).addCallback(
            lambda exc: self.assertEqual(exc.args[0], b"bogus login")
        )

    def testBadUsernameLogin(self):
        p, t = setUp()
        p.allowInsecureLogin = True
        d = p.login(b"username", b"password")
        self.assertEqual(t.value(), b"USER username\r\n")
        p.dataReceived(b"-ERR bogus login\r\n")
        return self.assertFailure(d, ServerErrorResponse).addCallback(
            lambda exc: self.assertEqual(exc.args[0], b"bogus login")
        )

    def testServerGreeting(self):
        p, t = setUp(greet=False)
        p.dataReceived(b"+OK lalala this has no challenge\r\n")
        self.assertEqual(p.serverChallenge, None)

    def testServerGreetingWithChallenge(self):
        p, t = setUp(greet=False)
        p.dataReceived(b"+OK <here is the challenge>\r\n")
        self.assertEqual(p.serverChallenge, b"<here is the challenge>")

    def testAPOP(self):
        p, t = setUp(greet=False)
        p.dataReceived(b"+OK <challenge string goes here>\r\n")
        d = p.login(b"username", b"password")
        self.assertEqual(
            t.value(), b"APOP username f34f1e464d0d7927607753129cabe39a\r\n"
        )
        p.dataReceived(b"+OK Welcome!\r\n")
        return d.addCallback(self.assertEqual, b"Welcome!")

    def testInsecureLoginRaisesException(self):
        p, t = setUp(greet=False)
        p.dataReceived(b"+OK Howdy\r\n")
        d = p.login(b"username", b"password")
        self.assertFalse(t.value())
        return self.assertFailure(d, InsecureAuthenticationDisallowed)

    def testSSLTransportConsideredSecure(self):
        """
        If a server doesn't offer APOP but the transport is secured using
        SSL or TLS, a plaintext login should be allowed, not rejected with
        an InsecureAuthenticationDisallowed exception.
        """
        p, t = setUp(greet=False)
        directlyProvides(t, interfaces.ISSLTransport)
        p.dataReceived(b"+OK Howdy\r\n")
        d = p.login(b"username", b"password")
        self.assertEqual(t.value(), b"USER username\r\n")
        t.clear()
        p.dataReceived(b"+OK\r\n")
        self.assertEqual(t.value(), b"PASS password\r\n")
        p.dataReceived(b"+OK\r\n")
        return d


class ListConsumer:
    def __init__(self):
        self.data = {}

    def consume(self, result):
        (item, value) = result
        self.data.setdefault(item, []).append(value)


class MessageConsumer:
    def __init__(self):
        self.data = []

    def consume(self, line):
        self.data.append(line)


class POP3ClientListTests(TestCase):
    def testListSize(self):
        p, t = setUp()
        d = p.listSize()
        self.assertEqual(t.value(), b"LIST\r\n")
        p.dataReceived(b"+OK Here it comes\r\n")
        p.dataReceived(b"1 3\r\n2 2\r\n3 1\r\n.\r\n")
        return d.addCallback(self.assertEqual, [3, 2, 1])

    def testListSizeWithConsumer(self):
        p, t = setUp()
        c = ListConsumer()
        f = c.consume
        d = p.listSize(f)
        self.assertEqual(t.value(), b"LIST\r\n")
        p.dataReceived(b"+OK Here it comes\r\n")
        p.dataReceived(b"1 3\r\n2 2\r\n3 1\r\n")
        self.assertEqual(c.data, {0: [3], 1: [2], 2: [1]})
        p.dataReceived(b"5 3\r\n6 2\r\n7 1\r\n")
        self.assertEqual(c.data, {0: [3], 1: [2], 2: [1], 4: [3], 5: [2], 6: [1]})
        p.dataReceived(b".\r\n")
        return d.addCallback(self.assertIdentical, f)

    def testFailedListSize(self):
        p, t = setUp()
        d = p.listSize()
        self.assertEqual(t.value(), b"LIST\r\n")
        p.dataReceived(b"-ERR Fatal doom server exploded\r\n")
        return self.assertFailure(d, ServerErrorResponse).addCallback(
            lambda exc: self.assertEqual(exc.args[0], b"Fatal doom server exploded")
        )

    def testListUID(self):
        p, t = setUp()
        d = p.listUID()
        self.assertEqual(t.value(), b"UIDL\r\n")
        p.dataReceived(b"+OK Here it comes\r\n")
        p.dataReceived(b"1 abc\r\n2 def\r\n3 ghi\r\n.\r\n")
        return d.addCallback(self.assertEqual, [b"abc", b"def", b"ghi"])

    def testListUIDWithConsumer(self):
        p, t = setUp()
        c = ListConsumer()
        f = c.consume
        d = p.listUID(f)
        self.assertEqual(t.value(), b"UIDL\r\n")
        p.dataReceived(b"+OK Here it comes\r\n")
        p.dataReceived(b"1 xyz\r\n2 abc\r\n5 mno\r\n")
        self.assertEqual(c.data, {0: [b"xyz"], 1: [b"abc"], 4: [b"mno"]})
        p.dataReceived(b".\r\n")
        return d.addCallback(self.assertIdentical, f)

    def testFailedListUID(self):
        p, t = setUp()
        d = p.listUID()
        self.assertEqual(t.value(), b"UIDL\r\n")
        p.dataReceived(b"-ERR Fatal doom server exploded\r\n")
        return self.assertFailure(d, ServerErrorResponse).addCallback(
            lambda exc: self.assertEqual(exc.args[0], b"Fatal doom server exploded")
        )


class POP3ClientMessageTests(TestCase):
    def testRetrieve(self):
        p, t = setUp()
        d = p.retrieve(7)
        self.assertEqual(t.value(), b"RETR 8\r\n")
        p.dataReceived(b"+OK Message incoming\r\n")
        p.dataReceived(b"La la la here is message text\r\n")
        p.dataReceived(b"..Further message text tra la la\r\n")
        p.dataReceived(b".\r\n")
        return d.addCallback(
            self.assertEqual,
            [b"La la la here is message text", b".Further message text tra la la"],
        )

    def testRetrieveWithConsumer(self):
        p, t = setUp()
        c = MessageConsumer()
        f = c.consume
        d = p.retrieve(7, f)
        self.assertEqual(t.value(), b"RETR 8\r\n")
        p.dataReceived(b"+OK Message incoming\r\n")
        p.dataReceived(b"La la la here is message text\r\n")
        p.dataReceived(b"..Further message text\r\n.\r\n")
        return d.addCallback(self._cbTestRetrieveWithConsumer, f, c)

    def _cbTestRetrieveWithConsumer(self, result, f, c):
        self.assertIdentical(result, f)
        self.assertEqual(
            c.data, [b"La la la here is message text", b".Further message text"]
        )

    def testPartialRetrieve(self):
        p, t = setUp()
        d = p.retrieve(7, lines=2)
        self.assertEqual(t.value(), b"TOP 8 2\r\n")
        p.dataReceived(b"+OK 2 lines on the way\r\n")
        p.dataReceived(b"Line the first!  Woop\r\n")
        p.dataReceived(b"Line the last!  Bye\r\n")
        p.dataReceived(b".\r\n")
        return d.addCallback(
            self.assertEqual, [b"Line the first!  Woop", b"Line the last!  Bye"]
        )

    def testPartialRetrieveWithConsumer(self):
        p, t = setUp()
        c = MessageConsumer()
        f = c.consume
        d = p.retrieve(7, f, lines=2)
        self.assertEqual(t.value(), b"TOP 8 2\r\n")
        p.dataReceived(b"+OK 2 lines on the way\r\n")
        p.dataReceived(b"Line the first!  Woop\r\n")
        p.dataReceived(b"Line the last!  Bye\r\n")
        p.dataReceived(b".\r\n")
        return d.addCallback(self._cbTestPartialRetrieveWithConsumer, f, c)

    def _cbTestPartialRetrieveWithConsumer(self, result, f, c):
        self.assertIdentical(result, f)
        self.assertEqual(c.data, [b"Line the first!  Woop", b"Line the last!  Bye"])

    def testFailedRetrieve(self):
        p, t = setUp()
        d = p.retrieve(0)
        self.assertEqual(t.value(), b"RETR 1\r\n")
        p.dataReceived(b"-ERR Fatal doom server exploded\r\n")
        return self.assertFailure(d, ServerErrorResponse).addCallback(
            lambda exc: self.assertEqual(exc.args[0], b"Fatal doom server exploded")
        )

    def test_concurrentRetrieves(self):
        """
        Issue three retrieve calls immediately without waiting for any to
        succeed and make sure they all do succeed eventually.
        """
        p, t = setUp()
        messages = [
            p.retrieve(i).addCallback(
                self.assertEqual,
                [b"First line of %d." % (i + 1,), b"Second line of %d." % (i + 1,)],
            )
            for i in range(3)
        ]

        for i in range(1, 4):
            self.assertEqual(t.value(), b"RETR %d\r\n" % (i,))
            t.clear()
            p.dataReceived(b"+OK 2 lines on the way\r\n")
            p.dataReceived(b"First line of %d.\r\n" % (i,))
            p.dataReceived(b"Second line of %d.\r\n" % (i,))
            self.assertEqual(t.value(), b"")
            p.dataReceived(b".\r\n")

        return defer.DeferredList(messages, fireOnOneErrback=True)


class POP3ClientMiscTests(TestCase):
    def testCapability(self):
        p, t = setUp()
        d = p.capabilities(useCache=0)
        self.assertEqual(t.value(), b"CAPA\r\n")
        p.dataReceived(b"+OK Capabilities on the way\r\n")
        p.dataReceived(b"X\r\nY\r\nZ\r\nA 1 2 3\r\nB 1 2\r\nC 1\r\n.\r\n")
        return d.addCallback(
            self.assertEqual,
            {
                b"X": None,
                b"Y": None,
                b"Z": None,
                b"A": [b"1", b"2", b"3"],
                b"B": [b"1", b"2"],
                b"C": [b"1"],
            },
        )

    def testCapabilityError(self):
        p, t = setUp()
        d = p.capabilities(useCache=0)
        self.assertEqual(t.value(), b"CAPA\r\n")
        p.dataReceived(b"-ERR This server is lame!\r\n")
        return d.addCallback(self.assertEqual, {})

    def testStat(self):
        p, t = setUp()
        d = p.stat()
        self.assertEqual(t.value(), b"STAT\r\n")
        p.dataReceived(b"+OK 1 1212\r\n")
        return d.addCallback(self.assertEqual, (1, 1212))

    def testStatError(self):
        p, t = setUp()
        d = p.stat()
        self.assertEqual(t.value(), b"STAT\r\n")
        p.dataReceived(b"-ERR This server is lame!\r\n")
        return self.assertFailure(d, ServerErrorResponse).addCallback(
            lambda exc: self.assertEqual(exc.args[0], b"This server is lame!")
        )

    def testNoop(self):
        p, t = setUp()
        d = p.noop()
        self.assertEqual(t.value(), b"NOOP\r\n")
        p.dataReceived(b"+OK No-op to you too!\r\n")
        return d.addCallback(self.assertEqual, b"No-op to you too!")

    def testNoopError(self):
        p, t = setUp()
        d = p.noop()
        self.assertEqual(t.value(), b"NOOP\r\n")
        p.dataReceived(b"-ERR This server is lame!\r\n")
        return self.assertFailure(d, ServerErrorResponse).addCallback(
            lambda exc: self.assertEqual(exc.args[0], b"This server is lame!")
        )

    def testRset(self):
        p, t = setUp()
        d = p.reset()
        self.assertEqual(t.value(), b"RSET\r\n")
        p.dataReceived(b"+OK Reset state\r\n")
        return d.addCallback(self.assertEqual, b"Reset state")

    def testRsetError(self):
        p, t = setUp()
        d = p.reset()
        self.assertEqual(t.value(), b"RSET\r\n")
        p.dataReceived(b"-ERR This server is lame!\r\n")
        return self.assertFailure(d, ServerErrorResponse).addCallback(
            lambda exc: self.assertEqual(exc.args[0], b"This server is lame!")
        )

    def testDelete(self):
        p, t = setUp()
        d = p.delete(3)
        self.assertEqual(t.value(), b"DELE 4\r\n")
        p.dataReceived(b"+OK Hasta la vista\r\n")
        return d.addCallback(self.assertEqual, b"Hasta la vista")

    def testDeleteError(self):
        p, t = setUp()
        d = p.delete(3)
        self.assertEqual(t.value(), b"DELE 4\r\n")
        p.dataReceived(b"-ERR Winner is not you.\r\n")
        return self.assertFailure(d, ServerErrorResponse).addCallback(
            lambda exc: self.assertEqual(exc.args[0], b"Winner is not you.")
        )


class SimpleClient(POP3Client):
    def __init__(self, deferred, contextFactory=None):
        self.deferred = deferred
        self.allowInsecureLogin = True

    def serverGreeting(self, challenge):
        self.deferred.callback(None)


class POP3HelperMixin:
    serverCTX = None
    clientCTX = None

    def setUp(self):
        d = defer.Deferred()
        self.server = pop3testserver.POP3TestServer(contextFactory=self.serverCTX)
        self.client = SimpleClient(d, contextFactory=self.clientCTX)
        self.client.timeout = 30
        self.connected = d

    def tearDown(self):
        del self.server
        del self.client
        del self.connected

    def _cbStopClient(self, ignore):
        self.client.transport.loseConnection()

    def _ebGeneral(self, failure):
        self.client.transport.loseConnection()
        self.server.transport.loseConnection()
        return failure

    def loopback(self):
        return loopback.loopbackTCP(self.server, self.client, noisy=False)


class TLSServerFactory(protocol.ServerFactory):
    class protocol(basic.LineReceiver):
        context = None
        output: List[bytes] = []

        def connectionMade(self):
            self.factory.input = []
            self.output = self.output[:]
            for line in self.output.pop(0):
                self.sendLine(line)

        def lineReceived(self, line):
            self.factory.input.append(line)
            [self.sendLine(l) for l in self.output.pop(0)]
            if line == b"STLS":
                self.transport.startTLS(self.context)


@skipIf(not ClientTLSContext, "OpenSSL not present")
@skipIf(not interfaces.IReactorSSL(reactor, None), "OpenSSL not present")
class POP3TLSTests(TestCase):
    """
    Tests for POP3Client's support for TLS connections.
    """

    def test_startTLS(self):
        """
        POP3Client.startTLS starts a TLS session over its existing TCP
        connection.
        """
        sf = TLSServerFactory()
        sf.protocol.output = [
            [b"+OK"],  # Server greeting
            [b"+OK", b"STLS", b"."],  # CAPA response
            [b"+OK"],  # STLS response
            [b"+OK", b"."],  # Second CAPA response
            [b"+OK"],  # QUIT response
        ]
        sf.protocol.context = ServerTLSContext()
        port = reactor.listenTCP(0, sf, interface="127.0.0.1")
        self.addCleanup(port.stopListening)
        H = port.getHost().host
        P = port.getHost().port

        connLostDeferred = defer.Deferred()
        cp = SimpleClient(defer.Deferred(), ClientTLSContext())

        def connectionLost(reason):
            SimpleClient.connectionLost(cp, reason)
            connLostDeferred.callback(None)

        cp.connectionLost = connectionLost
        cf = protocol.ClientFactory()
        cf.protocol = lambda: cp

        conn = reactor.connectTCP(H, P, cf)

        def cbConnected(ignored):
            log.msg("Connected to server; starting TLS")
            return cp.startTLS()

        def cbStartedTLS(ignored):
            log.msg("Started TLS; disconnecting")
            return cp.quit()

        def cbDisconnected(ign):
            log.msg("Disconnected; asserting correct input received")
            self.assertEqual(sf.input, [b"CAPA", b"STLS", b"CAPA", b"QUIT"])

        def cleanup(result):
            log.msg(
                "Asserted correct input; disconnecting "
                "client and shutting down server"
            )
            conn.disconnect()
            return connLostDeferred

        cp.deferred.addCallback(cbConnected)
        cp.deferred.addCallback(cbStartedTLS)
        cp.deferred.addCallback(cbDisconnected)
        cp.deferred.addBoth(cleanup)

        return cp.deferred


class POP3TimeoutTests(POP3HelperMixin, TestCase):
    def testTimeout(self):
        def login():
            d = self.client.login("test", "twisted")
            d.addCallback(loggedIn)
            d.addErrback(timedOut)
            return d

        def loggedIn(result):
            self.fail("Successfully logged in!?  Impossible!")

        def timedOut(failure):
            failure.trap(error.TimeoutError)
            self._cbStopClient(None)

        def quit():
            return self.client.quit()

        self.client.timeout = 0.01

        # Tell the server to not return a response to client.  This
        # will trigger a timeout.
        pop3testserver.TIMEOUT_RESPONSE = True

        methods = [login, quit]
        map(self.connected.addCallback, map(strip, methods))
        self.connected.addCallback(self._cbStopClient)
        self.connected.addErrback(self._ebGeneral)
        return self.loopback()


class POP3ClientModuleStructureTests(TestCase):
    """
    Miscellaneous tests more to do with module/package structure than
    anything to do with the POP3 client.
    """

    def test_all(self):
        """
        twisted.mail._pop3client.__all__ should be empty because all classes
        should be imported through twisted.mail.pop3.
        """
        self.assertEqual(twisted.mail._pop3client.__all__, [])

    def test_import(self):
        """
        Every public class in twisted.mail._pop3client should be available as
        a member of twisted.mail.pop3 with the exception of
        twisted.mail._pop3client.POP3Client which should be available as
        twisted.mail.pop3.AdvancedClient.
        """
        publicClasses = [
            c[0]
            for c in inspect.getmembers(
                sys.modules["twisted.mail._pop3client"], inspect.isclass
            )
            if not c[0][0] == "_"
        ]

        for pc in publicClasses:
            if not pc == "POP3Client":
                self.assertTrue(
                    hasattr(twisted.mail.pop3, pc),
                    f"{pc} not in {twisted.mail.pop3}",
                )
            else:
                self.assertTrue(hasattr(twisted.mail.pop3, "AdvancedPOP3Client"))
