# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for twisted.mail.smtp module.
"""


import base64
import inspect
import re
from io import BytesIO
from typing import Any, List, Optional, Tuple, Type

from zope.interface import directlyProvides, implementer

import twisted.cred.checkers
import twisted.cred.credentials
import twisted.cred.error
import twisted.cred.portal
from twisted import cred
from twisted.cred.checkers import AllowAnonymousAccess, ICredentialsChecker
from twisted.cred.credentials import IAnonymous
from twisted.cred.error import UnauthorizedLogin
from twisted.cred.portal import IRealm, Portal
from twisted.internet import address, defer, error, interfaces, protocol, reactor, task
from twisted.mail import smtp
from twisted.mail._cred import LOGINCredentials
from twisted.protocols import basic, loopback
from twisted.python.util import LineLog
from twisted.test.proto_helpers import MemoryReactor, StringTransport
from twisted.trial.unittest import TestCase

sslSkip: Optional[str]
try:
    from twisted.test.ssl_helpers import ClientTLSContext, ServerTLSContext
except ImportError:
    sslSkip = "OpenSSL not present"
else:
    sslSkip = None


if not interfaces.IReactorSSL.providedBy(reactor):
    sslSkip = "Reactor doesn't support SSL"


def spameater(*spam, **eggs):
    return None


@implementer(smtp.IMessage)
class BrokenMessage:
    """
    L{BrokenMessage} is an L{IMessage} which raises an unexpected exception
    from its C{eomReceived} method.  This is useful for creating a server which
    can be used to test client retry behavior.
    """

    def __init__(self, user):
        pass

    def lineReceived(self, line):
        pass

    def eomReceived(self):
        raise RuntimeError("Some problem, delivery is failing.")

    def connectionLost(self):
        pass


class DummyMessage:
    """
    L{BrokenMessage} is an L{IMessage} which saves the message delivered to it
    to its domain object.

    @ivar domain: A L{DummyDomain} which will be used to store the message once
        it is received.
    """

    def __init__(self, domain, user):
        self.domain = domain
        self.user = user
        self.buffer = []

    def lineReceived(self, line):
        # Throw away the generated Received: header
        if not re.match(br"Received: From yyy.com \(\[.*\]\) by localhost;", line):
            self.buffer.append(line)

    def eomReceived(self):
        message = b"\n".join(self.buffer) + b"\n"
        self.domain.messages[self.user.dest.local].append(message)
        deferred = defer.Deferred()
        deferred.callback(b"saved")
        return deferred


class DummyDomain:
    """
    L{DummyDomain} is an L{IDomain} which keeps track of messages delivered to
    it in memory.
    """

    def __init__(self, names):
        self.messages = {}
        for name in names:
            self.messages[name] = []

    def exists(self, user):
        if user.dest.local in self.messages:
            return defer.succeed(lambda: DummyMessage(self, user))
        return defer.fail(smtp.SMTPBadRcpt(user))


mail = b"""\
Subject: hello

Goodbye
"""


class MyClient:
    def __init__(self, messageInfo=None):
        if messageInfo is None:
            messageInfo = ("moshez@foo.bar", ["moshez@foo.bar"], BytesIO(mail))
        self._sender = messageInfo[0]
        self._recipient = messageInfo[1]
        self._data = messageInfo[2]

    def getMailFrom(self):
        return self._sender

    def getMailTo(self):
        return self._recipient

    def getMailData(self):
        return self._data

    def sendError(self, exc):
        self._error = exc

    def sentMail(self, code, resp, numOk, addresses, log):
        # Prevent another mail from being sent.
        self._sender = None
        self._recipient = None
        self._data = None


class MySMTPClient(MyClient, smtp.SMTPClient):
    def __init__(self, messageInfo=None):
        smtp.SMTPClient.__init__(self, b"foo.baz")
        MyClient.__init__(self, messageInfo)


class MyESMTPClient(MyClient, smtp.ESMTPClient):
    def __init__(self, secret=b"", contextFactory=None):
        smtp.ESMTPClient.__init__(self, secret, contextFactory, b"foo.baz")
        MyClient.__init__(self)


class LoopbackMixin:
    def loopback(self, server, client):
        return loopback.loopbackTCP(server, client)


class FakeSMTPServer(basic.LineReceiver):

    clientData = [
        b"220 hello",
        b"250 nice to meet you",
        b"250 great",
        b"250 great",
        b"354 go on, lad",
    ]

    def connectionMade(self):
        self.buffer = []
        self.clientData = self.clientData[:]
        self.clientData.reverse()
        self.sendLine(self.clientData.pop())

    def lineReceived(self, line):
        self.buffer.append(line)
        if line == b"QUIT":
            self.transport.write(b"221 see ya around\r\n")
            self.transport.loseConnection()
        elif line == b".":
            self.transport.write(b"250 gotcha\r\n")
        elif line == b"RSET":
            self.transport.loseConnection()

        if self.clientData:
            self.sendLine(self.clientData.pop())


class SMTPClientTests(TestCase, LoopbackMixin):
    """
    Tests for L{smtp.SMTPClient}.
    """

    def test_timeoutConnection(self):
        """
        L{smtp.SMTPClient.timeoutConnection} calls the C{sendError} hook with a
        fatal L{SMTPTimeoutError} with the current line log.
        """
        errors = []
        client = MySMTPClient()
        client.sendError = errors.append
        client.makeConnection(StringTransport())
        client.lineReceived(b"220 hello")
        client.timeoutConnection()
        self.assertIsInstance(errors[0], smtp.SMTPTimeoutError)
        self.assertTrue(errors[0].isFatal)
        self.assertEqual(
            bytes(errors[0]),
            b"Timeout waiting for SMTP server response\n"
            b"<<< 220 hello\n"
            b">>> HELO foo.baz\n",
        )

    expected_output = [
        b"HELO foo.baz",
        b"MAIL FROM:<moshez@foo.bar>",
        b"RCPT TO:<moshez@foo.bar>",
        b"DATA",
        b"Subject: hello",
        b"",
        b"Goodbye",
        b".",
        b"RSET",
    ]

    def test_messages(self):
        """
        L{smtp.SMTPClient} sends I{HELO}, I{MAIL FROM}, I{RCPT TO}, and I{DATA}
        commands based on the return values of its C{getMailFrom},
        C{getMailTo}, and C{getMailData} methods.
        """
        client = MySMTPClient()
        server = FakeSMTPServer()
        d = self.loopback(server, client)
        d.addCallback(lambda x: self.assertEqual(server.buffer, self.expected_output))
        return d

    def test_transferError(self):
        """
        If there is an error while producing the message body to the
        connection, the C{sendError} callback is invoked.
        """
        client = MySMTPClient(
            ("alice@example.com", ["bob@example.com"], BytesIO(b"foo"))
        )
        transport = StringTransport()
        client.makeConnection(transport)
        client.dataReceived(
            b"220 Ok\r\n"  # Greeting
            b"250 Ok\r\n"  # EHLO response
            b"250 Ok\r\n"  # MAIL FROM response
            b"250 Ok\r\n"  # RCPT TO response
            b"354 Ok\r\n"  # DATA response
        )

        # Sanity check - a pull producer should be registered now.
        self.assertNotIdentical(transport.producer, None)
        self.assertFalse(transport.streaming)

        # Now stop the producer prematurely, meaning the message was not sent.
        transport.producer.stopProducing()

        # The sendError hook should have been invoked as a result.
        self.assertIsInstance(client._error, Exception)

    def test_sendFatalError(self):
        """
        If L{smtp.SMTPClient.sendError} is called with an L{SMTPClientError}
        which is fatal, it disconnects its transport without writing anything
        more to it.
        """
        client = smtp.SMTPClient(None)
        transport = StringTransport()
        client.makeConnection(transport)
        client.sendError(smtp.SMTPClientError(123, "foo", isFatal=True))
        self.assertEqual(transport.value(), b"")
        self.assertTrue(transport.disconnecting)

    def test_sendNonFatalError(self):
        """
        If L{smtp.SMTPClient.sendError} is called with an L{SMTPClientError}
        which is not fatal, it sends C{"QUIT"} and waits for the server to
        close the connection.
        """
        client = smtp.SMTPClient(None)
        transport = StringTransport()
        client.makeConnection(transport)
        client.sendError(smtp.SMTPClientError(123, "foo", isFatal=False))
        self.assertEqual(transport.value(), b"QUIT\r\n")
        self.assertFalse(transport.disconnecting)

    def test_sendOtherError(self):
        """
        If L{smtp.SMTPClient.sendError} is called with an exception which is
        not an L{SMTPClientError}, it disconnects its transport without
        writing anything more to it.
        """
        client = smtp.SMTPClient(None)
        transport = StringTransport()
        client.makeConnection(transport)
        client.sendError(Exception("foo"))
        self.assertEqual(transport.value(), b"")
        self.assertTrue(transport.disconnecting)


class DummySMTPMessage:
    def __init__(self, protocol, users):
        self.protocol = protocol
        self.users = users
        self.buffer = []

    def lineReceived(self, line):
        self.buffer.append(line)

    def eomReceived(self):
        message = b"\n".join(self.buffer) + b"\n"
        helo, origin = self.users[0].helo[0], bytes(self.users[0].orig)
        recipients = []
        for user in self.users:
            recipients.append(bytes(user))
        self.protocol.message[tuple(recipients)] = (helo, origin, recipients, message)
        return defer.succeed(b"saved")


class DummyProto:
    def connectionMade(self):
        self.dummyMixinBase.connectionMade(self)
        self.message = {}

    def receivedHeader(*spam):
        return None

    def validateTo(self, user):
        self.delivery = SimpleDelivery(None)
        return lambda: DummySMTPMessage(self, [user])

    def validateFrom(self, helo, origin):
        return origin


class DummySMTP(DummyProto, smtp.SMTP):
    dummyMixinBase = smtp.SMTP


class DummyESMTP(DummyProto, smtp.ESMTP):
    dummyMixinBase = smtp.ESMTP


class AnotherTestCase:
    serverClass: Optional[Type[protocol.Protocol]] = None
    clientClass: Optional[Type[smtp.SMTPClient]] = None

    messages = [
        (
            b"foo.com",
            b"moshez@foo.com",
            [b"moshez@bar.com"],
            b"moshez@foo.com",
            [b"moshez@bar.com"],
            b"""\
From: Moshe
To: Moshe

Hi,
how are you?
""",
        ),
        (
            b"foo.com",
            b"tttt@rrr.com",
            [b"uuu@ooo", b"yyy@eee"],
            b"tttt@rrr.com",
            [b"uuu@ooo", b"yyy@eee"],
            b"""\
Subject: pass

..rrrr..
""",
        ),
        (
            b"foo.com",
            b"@this,@is,@ignored:foo@bar.com",
            [b"@ignore,@this,@too:bar@foo.com"],
            b"foo@bar.com",
            [b"bar@foo.com"],
            b"""\
Subject: apa
To: foo

123
.
456
""",
        ),
    ]

    data: List[Tuple[bytes, bytes, Any, Any]] = [
        (b"", b"220.*\r\n$", None, None),
        (b"HELO foo.com\r\n", b"250.*\r\n$", None, None),
        (b"RSET\r\n", b"250.*\r\n$", None, None),
    ]
    for helo_, from_, to_, realfrom, realto, msg in messages:
        data.append((b"MAIL FROM:<" + from_ + b">\r\n", b"250.*\r\n", None, None))
        for rcpt in to_:
            data.append((b"RCPT TO:<" + rcpt + b">\r\n", b"250.*\r\n", None, None))

        data.append(
            (
                b"DATA\r\n",
                b"354.*\r\n",
                msg,
                (b"250.*\r\n", (helo_, realfrom, realto, msg)),
            )
        )

    def test_buffer(self):
        """
        Exercise a lot of the SMTP client code.  This is a "shotgun" style unit
        test.  It does a lot of things and hopes that something will go really
        wrong if it is going to go wrong.  This test should be replaced with a
        suite of nicer tests.
        """
        transport = StringTransport()
        a = self.serverClass()

        class fooFactory:
            domain = b"foo.com"

        a.factory = fooFactory()
        a.makeConnection(transport)
        for (send, expect, msg, msgexpect) in self.data:
            if send:
                a.dataReceived(send)
            data = transport.value()
            transport.clear()
            if not re.match(expect, data):
                raise AssertionError(send, expect, data)
            if data[:3] == b"354":
                for line in msg.splitlines():
                    if line and line[0:1] == b".":
                        line = b"." + line
                    a.dataReceived(line + b"\r\n")
                a.dataReceived(b".\r\n")
                # Special case for DATA. Now we want a 250, and then
                # we compare the messages
                data = transport.value()
                transport.clear()
                resp, msgdata = msgexpect
                if not re.match(resp, data):
                    raise AssertionError(resp, data)
                for recip in msgdata[2]:
                    expected = list(msgdata[:])
                    expected[2] = [recip]
                    self.assertEqual(a.message[(recip,)], tuple(expected))
        a.setTimeout(None)


class AnotherESMTPTests(AnotherTestCase, TestCase):
    serverClass = DummyESMTP
    clientClass = MyESMTPClient


class AnotherSMTPTests(AnotherTestCase, TestCase):
    serverClass = DummySMTP
    clientClass = MySMTPClient


@implementer(cred.checkers.ICredentialsChecker)
class DummyChecker:
    users = {b"testuser": b"testpassword"}

    credentialInterfaces = (
        cred.credentials.IUsernamePassword,
        cred.credentials.IUsernameHashedPassword,
    )

    def requestAvatarId(self, credentials):
        return defer.maybeDeferred(
            credentials.checkPassword, self.users[credentials.username]
        ).addCallback(self._cbCheck, credentials.username)

    def _cbCheck(self, result, username):
        if result:
            return username
        raise cred.error.UnauthorizedLogin()


@implementer(smtp.IMessageDelivery)
class SimpleDelivery:
    """
    L{SimpleDelivery} is a message delivery factory with no interesting
    behavior.
    """

    def __init__(self, messageFactory):
        self._messageFactory = messageFactory

    def receivedHeader(self, helo, origin, recipients):
        return None

    def validateFrom(self, helo, origin):
        return origin

    def validateTo(self, user):
        return lambda: self._messageFactory(user)


class DummyRealm:
    def requestAvatar(self, avatarId, mind, *interfaces):
        return smtp.IMessageDelivery, SimpleDelivery(None), lambda: None


class AuthTests(TestCase, LoopbackMixin):
    def test_crammd5Auth(self):
        """
        L{ESMTPClient} can authenticate using the I{CRAM-MD5} SASL mechanism.

        @see: U{http://tools.ietf.org/html/rfc2195}
        """
        realm = DummyRealm()
        p = cred.portal.Portal(realm)
        p.registerChecker(DummyChecker())

        server = DummyESMTP({b"CRAM-MD5": cred.credentials.CramMD5Credentials})
        server.portal = p
        client = MyESMTPClient(b"testpassword")

        cAuth = smtp.CramMD5ClientAuthenticator(b"testuser")
        client.registerAuthenticator(cAuth)

        d = self.loopback(server, client)
        d.addCallback(lambda x: self.assertEqual(server.authenticated, 1))
        return d

    def test_loginAuth(self):
        """
        L{ESMTPClient} can authenticate using the I{LOGIN} SASL mechanism.

        @see: U{http://sepp.oetiker.ch/sasl-2.1.19-ds/draft-murchison-sasl-login-00.txt}
        """
        realm = DummyRealm()
        p = cred.portal.Portal(realm)
        p.registerChecker(DummyChecker())

        server = DummyESMTP({b"LOGIN": LOGINCredentials})
        server.portal = p
        client = MyESMTPClient(b"testpassword")

        cAuth = smtp.LOGINAuthenticator(b"testuser")
        client.registerAuthenticator(cAuth)

        d = self.loopback(server, client)
        d.addCallback(lambda x: self.assertTrue(server.authenticated))
        return d

    def test_loginAgainstWeirdServer(self):
        """
        When communicating with a server which implements the I{LOGIN} SASL
        mechanism using C{"Username:"} as the challenge (rather than C{"User
        Name\\0"}), L{ESMTPClient} can still authenticate successfully using
        the I{LOGIN} mechanism.
        """
        realm = DummyRealm()
        p = cred.portal.Portal(realm)
        p.registerChecker(DummyChecker())

        server = DummyESMTP({b"LOGIN": smtp.LOGINCredentials})
        server.portal = p

        client = MyESMTPClient(b"testpassword")
        cAuth = smtp.LOGINAuthenticator(b"testuser")
        client.registerAuthenticator(cAuth)

        d = self.loopback(server, client)
        d.addCallback(lambda x: self.assertTrue(server.authenticated))
        return d


class SMTPHelperTests(TestCase):
    def testMessageID(self):
        d = {}
        for i in range(1000):
            m = smtp.messageid("testcase")
            self.assertFalse(m in d)
            d[m] = None

    def testQuoteAddr(self):
        cases = [
            [b"user@host.name", b"<user@host.name>"],
            [b'"User Name" <user@host.name>', b"<user@host.name>"],
            [smtp.Address(b"someguy@someplace"), b"<someguy@someplace>"],
            [b"", b"<>"],
            [smtp.Address(b""), b"<>"],
        ]

        for (c, e) in cases:
            self.assertEqual(smtp.quoteaddr(c), e)

    def testUser(self):
        u = smtp.User(b"user@host", b"helo.host.name", None, None)
        self.assertEqual(str(u), "user@host")

    def testXtextEncoding(self):
        cases = [
            ("Hello world", b"Hello+20world"),
            ("Hello+world", b"Hello+2Bworld"),
            ("\0\1\2\3\4\5", b"+00+01+02+03+04+05"),
            ("e=mc2@example.com", b"e+3Dmc2@example.com"),
        ]

        for (case, expected) in cases:
            self.assertEqual(smtp.xtext_encode(case), (expected, len(case)))
            self.assertEqual(case.encode("xtext"), expected)
            self.assertEqual(smtp.xtext_decode(expected), (case, len(expected)))
            self.assertEqual(expected.decode("xtext"), case)

    def test_encodeWithErrors(self):
        """
        Specifying an error policy to C{unicode.encode} with the
        I{xtext} codec should produce the same result as not
        specifying the error policy.
        """
        text = "Hello world"
        self.assertEqual(
            smtp.xtext_encode(text, "strict"), (text.encode("xtext"), len(text))
        )
        self.assertEqual(text.encode("xtext", "strict"), text.encode("xtext"))

    def test_decodeWithErrors(self):
        """
        Similar to L{test_encodeWithErrors}, but for C{bytes.decode}.
        """
        bytes = b"Hello world"
        self.assertEqual(
            smtp.xtext_decode(bytes, "strict"), (bytes.decode("xtext"), len(bytes))
        )
        self.assertEqual(bytes.decode("xtext", "strict"), bytes.decode("xtext"))


class NoticeTLSClient(MyESMTPClient):
    tls = False

    def esmtpState_starttls(self, code, resp):
        MyESMTPClient.esmtpState_starttls(self, code, resp)
        self.tls = True


class TLSTests(TestCase, LoopbackMixin):
    skip = sslSkip

    def testTLS(self):
        clientCTX = ClientTLSContext()
        serverCTX = ServerTLSContext()

        client = NoticeTLSClient(contextFactory=clientCTX)
        server = DummyESMTP(contextFactory=serverCTX)

        def check(ignored):
            self.assertEqual(client.tls, True)
            self.assertEqual(server.startedTLS, True)

        return self.loopback(server, client).addCallback(check)


class EmptyLineTests(TestCase):
    def test_emptyLineSyntaxError(self):
        """
        If L{smtp.SMTP} receives an empty line, it responds with a 500 error
        response code and a message about a syntax error.
        """
        proto = smtp.SMTP()
        transport = StringTransport()
        proto.makeConnection(transport)
        proto.lineReceived(b"")
        proto.setTimeout(None)

        out = transport.value().splitlines()
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0].startswith(b"220"))
        self.assertEqual(out[1], b"500 Error: bad syntax")


class TimeoutTests(TestCase, LoopbackMixin):
    """
    Check that SMTP client factories correctly use the timeout.
    """

    def _timeoutTest(self, onDone, clientFactory):
        """
        Connect the clientFactory, and check the timeout on the request.
        """
        clock = task.Clock()
        client = clientFactory.buildProtocol(
            address.IPv4Address("TCP", "example.net", 25)
        )
        client.callLater = clock.callLater
        t = StringTransport()
        client.makeConnection(t)
        t.protocol = client

        def check(ign):
            self.assertEqual(clock.seconds(), 0.5)

        d = self.assertFailure(onDone, smtp.SMTPTimeoutError).addCallback(check)
        # The first call should not trigger the timeout
        clock.advance(0.1)
        # But this one should
        clock.advance(0.4)
        return d

    def test_SMTPClientRecipientBytes(self):
        """
        Test timeout for L{smtp.SMTPSenderFactory}: the response L{Deferred}
        should be errback with a L{smtp.SMTPTimeoutError}.
        """
        onDone = defer.Deferred()
        clientFactory = smtp.SMTPSenderFactory(
            "source@address",
            b"recipient@address",
            BytesIO(b"Message body"),
            onDone,
            retries=0,
            timeout=0.5,
        )
        return self._timeoutTest(onDone, clientFactory)

    def test_SMTPClientRecipientUnicode(self):
        """
        Use a L{unicode} recipient.
        """
        onDone = defer.Deferred()
        clientFactory = smtp.SMTPSenderFactory(
            "source@address",
            "recipient@address",
            BytesIO(b"Message body"),
            onDone,
            retries=0,
            timeout=0.5,
        )
        return self._timeoutTest(onDone, clientFactory)

    def test_SMTPClientRecipientList(self):
        """
        Use a L{list} of recipients.
        """
        onDone = defer.Deferred()
        clientFactory = smtp.SMTPSenderFactory(
            "source@address",
            ("recipient1@address", b"recipient2@address"),
            BytesIO(b"Message body"),
            onDone,
            retries=0,
            timeout=0.5,
        )
        return self._timeoutTest(onDone, clientFactory)

    def test_ESMTPClient(self):
        """
        Test timeout for L{smtp.ESMTPSenderFactory}: the response L{Deferred}
        should be errback with a L{smtp.SMTPTimeoutError}.
        """
        onDone = defer.Deferred()
        clientFactory = smtp.ESMTPSenderFactory(
            "username",
            "password",
            "source@address",
            "recipient@address",
            BytesIO(b"Message body"),
            onDone,
            retries=0,
            timeout=0.5,
        )
        return self._timeoutTest(onDone, clientFactory)

    def test_resetTimeoutWhileSending(self):
        """
        The timeout is not allowed to expire after the server has accepted a
        DATA command and the client is actively sending data to it.
        """

        class SlowFile:
            """
            A file-like which returns one byte from each read call until the
            specified number of bytes have been returned.
            """

            def __init__(self, size):
                self._size = size

            def read(self, max=None):
                if self._size:
                    self._size -= 1
                    return b"x"
                return b""

        failed = []
        onDone = defer.Deferred()
        onDone.addErrback(failed.append)
        clientFactory = smtp.SMTPSenderFactory(
            "source@address",
            "recipient@address",
            SlowFile(1),
            onDone,
            retries=0,
            timeout=3,
        )
        clientFactory.domain = b"example.org"
        clock = task.Clock()
        client = clientFactory.buildProtocol(
            address.IPv4Address("TCP", "example.net", 25)
        )
        client.callLater = clock.callLater
        transport = StringTransport()
        client.makeConnection(transport)

        client.dataReceived(
            b"220 Ok\r\n"  # Greet the client
            b"250 Ok\r\n"  # Respond to HELO
            b"250 Ok\r\n"  # Respond to MAIL FROM
            b"250 Ok\r\n"  # Respond to RCPT TO
            b"354 Ok\r\n"  # Respond to DATA
        )

        # Now the client is producing data to the server.  Any time
        # resumeProducing is called on the producer, the timeout should be
        # extended.  First, a sanity check.  This test is only written to
        # handle pull producers.
        self.assertNotIdentical(transport.producer, None)
        self.assertFalse(transport.streaming)

        # Now, allow 2 seconds (1 less than the timeout of 3 seconds) to
        # elapse.
        clock.advance(2)

        # The timeout has not expired, so the failure should not have happened.
        self.assertEqual(failed, [])

        # Let some bytes be produced, extending the timeout.  Then advance the
        # clock some more and verify that the timeout still hasn't happened.
        transport.producer.resumeProducing()
        clock.advance(2)
        self.assertEqual(failed, [])

        # The file has been completely produced - the next resume producing
        # finishes the upload, successfully.
        transport.producer.resumeProducing()
        client.dataReceived(b"250 Ok\r\n")
        self.assertEqual(failed, [])

        # Verify that the client actually did send the things expected.
        self.assertEqual(
            transport.value(),
            b"HELO example.org\r\n"
            b"MAIL FROM:<source@address>\r\n"
            b"RCPT TO:<recipient@address>\r\n"
            b"DATA\r\n"
            b"x\r\n"
            b".\r\n"
            # This RSET is just an implementation detail.  It's nice, but this
            # test doesn't really care about it.
            b"RSET\r\n",
        )


class MultipleDeliveryFactorySMTPServerFactory(protocol.ServerFactory):
    """
    L{MultipleDeliveryFactorySMTPServerFactory} creates SMTP server protocol
    instances with message delivery factory objects supplied to it.  Each
    factory is used for one connection and then discarded.  Factories are used
    in the order they are supplied.
    """

    def __init__(self, messageFactories):
        self._messageFactories = messageFactories

    def buildProtocol(self, addr):
        p = protocol.ServerFactory.buildProtocol(self, addr)
        p.delivery = SimpleDelivery(self._messageFactories.pop(0))
        return p


class SMTPSenderFactoryTests(TestCase):
    """
    Tests for L{smtp.SMTPSenderFactory}.
    """

    def test_removeCurrentProtocolWhenClientConnectionLost(self):
        """
        L{smtp.SMTPSenderFactory} removes the current protocol when the client
        connection is lost.
        """
        reactor = MemoryReactor()
        sentDeferred = defer.Deferred()
        clientFactory = smtp.SMTPSenderFactory(
            "source@address", "recipient@address", BytesIO(b"message"), sentDeferred
        )
        connector = reactor.connectTCP("localhost", 25, clientFactory)
        clientFactory.buildProtocol(None)
        clientFactory.clientConnectionLost(connector, error.ConnectionDone("Bye."))
        self.assertEqual(clientFactory.currentProtocol, None)

    def test_removeCurrentProtocolWhenClientConnectionFailed(self):
        """
        L{smtp.SMTPSenderFactory} removes the current protocol when the client
        connection is failed.
        """
        reactor = MemoryReactor()
        sentDeferred = defer.Deferred()
        clientFactory = smtp.SMTPSenderFactory(
            "source@address", "recipient@address", BytesIO(b"message"), sentDeferred
        )
        connector = reactor.connectTCP("localhost", 25, clientFactory)
        clientFactory.buildProtocol(None)
        clientFactory.clientConnectionFailed(connector, error.ConnectionDone("Bye."))
        self.assertEqual(clientFactory.currentProtocol, None)


class SMTPSenderFactoryRetryTests(TestCase):
    """
    Tests for the retry behavior of L{smtp.SMTPSenderFactory}.
    """

    def test_retryAfterDisconnect(self):
        """
        If the protocol created by L{SMTPSenderFactory} loses its connection
        before receiving confirmation of message delivery, it reconnects and
        tries to deliver the message again.
        """
        recipient = b"alice"
        message = b"some message text"
        domain = DummyDomain([recipient])

        class CleanSMTP(smtp.SMTP):
            """
            An SMTP subclass which ensures that its transport will be
            disconnected before the test ends.
            """

            def makeConnection(innerSelf, transport):
                self.addCleanup(transport.loseConnection)
                smtp.SMTP.makeConnection(innerSelf, transport)

        # Create a server which will fail the first message deliver attempt to
        # it with a 500 and a disconnect, but which will accept a message
        # delivered over the 2nd connection to it.
        serverFactory = MultipleDeliveryFactorySMTPServerFactory(
            [BrokenMessage, lambda user: DummyMessage(domain, user)]
        )
        serverFactory.protocol = CleanSMTP
        serverPort = reactor.listenTCP(0, serverFactory, interface="127.0.0.1")
        serverHost = serverPort.getHost()
        self.addCleanup(serverPort.stopListening)

        # Set up a client to try to deliver a message to the above created
        # server.
        sentDeferred = defer.Deferred()
        clientFactory = smtp.SMTPSenderFactory(
            b"bob@example.org",
            recipient + b"@example.com",
            BytesIO(message),
            sentDeferred,
        )
        clientFactory.domain = b"example.org"
        clientConnector = reactor.connectTCP(
            serverHost.host, serverHost.port, clientFactory
        )
        self.addCleanup(clientConnector.disconnect)

        def cbSent(ignored):
            """
            Verify that the message was successfully delivered and flush the
            error which caused the first attempt to fail.
            """
            self.assertEqual(domain.messages, {recipient: [b"\n" + message + b"\n"]})
            # Flush the RuntimeError that BrokenMessage caused to be logged.
            self.assertEqual(len(self.flushLoggedErrors(RuntimeError)), 1)

        sentDeferred.addCallback(cbSent)
        return sentDeferred


@implementer(IRealm)
class SingletonRealm:
    """
    Trivial realm implementation which is constructed with an interface and an
    avatar and returns that avatar when asked for that interface.
    """

    def __init__(self, interface, avatar):
        self.interface = interface
        self.avatar = avatar

    def requestAvatar(self, avatarId, mind, *interfaces):
        for iface in interfaces:
            if iface is self.interface:
                return iface, self.avatar, lambda: None


class NotImplementedDelivery:
    """
    Non-implementation of L{smtp.IMessageDelivery} which only has methods which
    raise L{NotImplementedError}.  Subclassed by various tests to provide the
    particular behavior being tested.
    """

    def validateFrom(self, helo, origin):
        raise NotImplementedError("This oughtn't be called in the course of this test.")

    def validateTo(self, user):
        raise NotImplementedError("This oughtn't be called in the course of this test.")

    def receivedHeader(self, helo, origin, recipients):
        raise NotImplementedError("This oughtn't be called in the course of this test.")


class SMTPServerTests(TestCase):
    """
    Test various behaviors of L{twisted.mail.smtp.SMTP} and
    L{twisted.mail.smtp.ESMTP}.
    """

    def testSMTPGreetingHost(self, serverClass=smtp.SMTP):
        """
        Test that the specified hostname shows up in the SMTP server's
        greeting.
        """
        s = serverClass()
        s.host = b"example.com"
        t = StringTransport()
        s.makeConnection(t)
        s.connectionLost(error.ConnectionDone())
        self.assertIn(b"example.com", t.value())

    def testSMTPGreetingNotExtended(self):
        """
        Test that the string "ESMTP" does not appear in the SMTP server's
        greeting since that string strongly suggests the presence of support
        for various SMTP extensions which are not supported by L{smtp.SMTP}.
        """
        s = smtp.SMTP()
        t = StringTransport()
        s.makeConnection(t)
        s.connectionLost(error.ConnectionDone())
        self.assertNotIn(b"ESMTP", t.value())

    def testESMTPGreetingHost(self):
        """
        Similar to testSMTPGreetingHost, but for the L{smtp.ESMTP} class.
        """
        self.testSMTPGreetingHost(smtp.ESMTP)

    def testESMTPGreetingExtended(self):
        """
        Test that the string "ESMTP" does appear in the ESMTP server's
        greeting since L{smtp.ESMTP} does support the SMTP extensions which
        that advertises to the client.
        """
        s = smtp.ESMTP()
        t = StringTransport()
        s.makeConnection(t)
        s.connectionLost(error.ConnectionDone())
        self.assertIn(b"ESMTP", t.value())

    def test_SMTPUnknownCommand(self):
        """
        Sending an unimplemented command is responded to with a 500.
        """
        s = smtp.SMTP()
        t = StringTransport()
        s.makeConnection(t)
        s.lineReceived(b"DOAGOODTHING")
        s.connectionLost(error.ConnectionDone())
        self.assertIn(b"500 Command not implemented", t.value())

    def test_acceptSenderAddress(self):
        """
        Test that a C{MAIL FROM} command with an acceptable address is
        responded to with the correct success code.
        """

        class AcceptanceDelivery(NotImplementedDelivery):
            """
            Delivery object which accepts all senders as valid.
            """

            def validateFrom(self, helo, origin):
                return origin

        realm = SingletonRealm(smtp.IMessageDelivery, AcceptanceDelivery())
        portal = Portal(realm, [AllowAnonymousAccess()])
        proto = smtp.SMTP()
        proto.portal = portal
        trans = StringTransport()
        proto.makeConnection(trans)

        # Deal with the necessary preliminaries
        proto.dataReceived(b"HELO example.com\r\n")
        trans.clear()

        # Try to specify our sender address
        proto.dataReceived(b"MAIL FROM:<alice@example.com>\r\n")

        # Clean up the protocol before doing anything that might raise an
        # exception.
        proto.connectionLost(error.ConnectionLost())

        # Make sure that we received exactly the correct response
        self.assertEqual(trans.value(), b"250 Sender address accepted\r\n")

    def test_deliveryRejectedSenderAddress(self):
        """
        Test that a C{MAIL FROM} command with an address rejected by a
        L{smtp.IMessageDelivery} instance is responded to with the correct
        error code.
        """

        class RejectionDelivery(NotImplementedDelivery):
            """
            Delivery object which rejects all senders as invalid.
            """

            def validateFrom(self, helo, origin):
                raise smtp.SMTPBadSender(origin)

        realm = SingletonRealm(smtp.IMessageDelivery, RejectionDelivery())
        portal = Portal(realm, [AllowAnonymousAccess()])
        proto = smtp.SMTP()
        proto.portal = portal
        trans = StringTransport()
        proto.makeConnection(trans)

        # Deal with the necessary preliminaries
        proto.dataReceived(b"HELO example.com\r\n")
        trans.clear()

        # Try to specify our sender address
        proto.dataReceived(b"MAIL FROM:<alice@example.com>\r\n")

        # Clean up the protocol before doing anything that might raise an
        # exception.
        proto.connectionLost(error.ConnectionLost())

        # Make sure that we received exactly the correct response
        self.assertEqual(
            trans.value(),
            b"550 Cannot receive from specified address "
            b"<alice@example.com>: Sender not acceptable\r\n",
        )

    @implementer(ICredentialsChecker)
    def test_portalRejectedSenderAddress(self):
        """
        Test that a C{MAIL FROM} command with an address rejected by an
        L{smtp.SMTP} instance's portal is responded to with the correct error
        code.
        """

        class DisallowAnonymousAccess:
            """
            Checker for L{IAnonymous} which rejects authentication attempts.
            """

            credentialInterfaces = (IAnonymous,)

            def requestAvatarId(self, credentials):
                return defer.fail(UnauthorizedLogin())

        realm = SingletonRealm(smtp.IMessageDelivery, NotImplementedDelivery())
        portal = Portal(realm, [DisallowAnonymousAccess()])
        proto = smtp.SMTP()
        proto.portal = portal
        trans = StringTransport()
        proto.makeConnection(trans)

        # Deal with the necessary preliminaries
        proto.dataReceived(b"HELO example.com\r\n")
        trans.clear()

        # Try to specify our sender address
        proto.dataReceived(b"MAIL FROM:<alice@example.com>\r\n")

        # Clean up the protocol before doing anything that might raise an
        # exception.
        proto.connectionLost(error.ConnectionLost())

        # Make sure that we received exactly the correct response
        self.assertEqual(
            trans.value(),
            b"550 Cannot receive from specified address "
            b"<alice@example.com>: Sender not acceptable\r\n",
        )

    def test_portalRejectedAnonymousSender(self):
        """
        Test that a C{MAIL FROM} command issued without first authenticating
        when a portal has been configured to disallow anonymous logins is
        responded to with the correct error code.
        """
        realm = SingletonRealm(smtp.IMessageDelivery, NotImplementedDelivery())
        portal = Portal(realm, [])
        proto = smtp.SMTP()
        proto.portal = portal
        trans = StringTransport()
        proto.makeConnection(trans)

        # Deal with the necessary preliminaries
        proto.dataReceived(b"HELO example.com\r\n")
        trans.clear()

        # Try to specify our sender address
        proto.dataReceived(b"MAIL FROM:<alice@example.com>\r\n")

        # Clean up the protocol before doing anything that might raise an
        # exception.
        proto.connectionLost(error.ConnectionLost())

        # Make sure that we received exactly the correct response
        self.assertEqual(
            trans.value(),
            b"550 Cannot receive from specified address "
            b"<alice@example.com>: Unauthenticated senders not allowed\r\n",
        )


class ESMTPAuthenticationTests(TestCase):
    def assertServerResponse(self, bytes, response):
        """
        Assert that when the given bytes are delivered to the ESMTP server
        instance, it responds with the indicated lines.

        @type bytes: str
        @type response: list of str
        """
        self.transport.clear()
        self.server.dataReceived(bytes)
        self.assertEqual(response, self.transport.value().splitlines())

    def assertServerAuthenticated(
        self, loginArgs, username=b"username", password=b"password"
    ):
        """
        Assert that a login attempt has been made, that the credentials and
        interfaces passed to it are correct, and that when the login request
        is satisfied, a successful response is sent by the ESMTP server
        instance.

        @param loginArgs: A C{list} previously passed to L{portalFactory}.
        @param username: The login user.
        @param password: The login password.
        """
        d, credentials, mind, interfaces = loginArgs.pop()
        self.assertEqual(loginArgs, [])
        self.assertTrue(
            twisted.cred.credentials.IUsernamePassword.providedBy(credentials)
        )
        self.assertEqual(credentials.username, username)
        self.assertTrue(credentials.checkPassword(password))
        self.assertIn(smtp.IMessageDeliveryFactory, interfaces)
        self.assertIn(smtp.IMessageDelivery, interfaces)
        d.callback((smtp.IMessageDeliveryFactory, None, lambda: None))

        self.assertEqual(
            [b"235 Authentication successful."], self.transport.value().splitlines()
        )

    def setUp(self):
        """
        Create an ESMTP instance attached to a StringTransport.
        """
        self.server = smtp.ESMTP({b"LOGIN": LOGINCredentials})
        self.server.host = b"localhost"
        self.transport = StringTransport(
            peerAddress=address.IPv4Address("TCP", "127.0.0.1", 12345)
        )
        self.server.makeConnection(self.transport)

    def tearDown(self):
        """
        Disconnect the ESMTP instance to clean up its timeout DelayedCall.
        """
        self.server.connectionLost(error.ConnectionDone())

    def portalFactory(self, loginList):
        class DummyPortal:
            def login(self, credentials, mind, *interfaces):
                d = defer.Deferred()
                loginList.append((d, credentials, mind, interfaces))
                return d

        return DummyPortal()

    def test_authenticationCapabilityAdvertised(self):
        """
        Test that AUTH is advertised to clients which issue an EHLO command.
        """
        self.transport.clear()
        self.server.dataReceived(b"EHLO\r\n")
        responseLines = self.transport.value().splitlines()
        self.assertEqual(
            responseLines[0], b"250-localhost Hello 127.0.0.1, nice to meet you"
        )
        self.assertEqual(responseLines[1], b"250 AUTH LOGIN")
        self.assertEqual(len(responseLines), 2)

    def test_plainAuthentication(self):
        """
        Test that the LOGIN authentication mechanism can be used
        """
        loginArgs = []
        self.server.portal = self.portalFactory(loginArgs)

        self.server.dataReceived(b"EHLO\r\n")
        self.transport.clear()

        self.assertServerResponse(
            b"AUTH LOGIN\r\n", [b"334 " + base64.b64encode(b"User Name\0").strip()]
        )

        self.assertServerResponse(
            base64.b64encode(b"username") + b"\r\n",
            [b"334 " + base64.b64encode(b"Password\0").strip()],
        )

        self.assertServerResponse(base64.b64encode(b"password").strip() + b"\r\n", [])

        self.assertServerAuthenticated(loginArgs)

    def test_plainAuthenticationEmptyPassword(self):
        """
        Test that giving an empty password for plain auth succeeds.
        """
        loginArgs = []
        self.server.portal = self.portalFactory(loginArgs)

        self.server.dataReceived(b"EHLO\r\n")
        self.transport.clear()

        self.assertServerResponse(
            b"AUTH LOGIN\r\n", [b"334 " + base64.b64encode(b"User Name\0").strip()]
        )

        self.assertServerResponse(
            base64.b64encode(b"username") + b"\r\n",
            [b"334 " + base64.b64encode(b"Password\0").strip()],
        )

        self.assertServerResponse(b"\r\n", [])
        self.assertServerAuthenticated(loginArgs, password=b"")

    def test_plainAuthenticationInitialResponse(self):
        """
        The response to the first challenge may be included on the AUTH command
        line.  Test that this is also supported.
        """
        loginArgs = []
        self.server.portal = self.portalFactory(loginArgs)

        self.server.dataReceived(b"EHLO\r\n")
        self.transport.clear()

        self.assertServerResponse(
            b"AUTH LOGIN " + base64.b64encode(b"username").strip() + b"\r\n",
            [b"334 " + base64.b64encode(b"Password\0").strip()],
        )

        self.assertServerResponse(base64.b64encode(b"password").strip() + b"\r\n", [])

        self.assertServerAuthenticated(loginArgs)

    def test_abortAuthentication(self):
        """
        Test that a challenge/response sequence can be aborted by the client.
        """
        loginArgs = []
        self.server.portal = self.portalFactory(loginArgs)

        self.server.dataReceived(b"EHLO\r\n")
        self.server.dataReceived(b"AUTH LOGIN\r\n")

        self.assertServerResponse(b"*\r\n", [b"501 Authentication aborted"])

    def test_invalidBase64EncodedResponse(self):
        """
        Test that a response which is not properly Base64 encoded results in
        the appropriate error code.
        """
        loginArgs = []
        self.server.portal = self.portalFactory(loginArgs)

        self.server.dataReceived(b"EHLO\r\n")
        self.server.dataReceived(b"AUTH LOGIN\r\n")

        self.assertServerResponse(
            b"x\r\n", [b"501 Syntax error in parameters or arguments"]
        )

        self.assertEqual(loginArgs, [])

    def test_invalidBase64EncodedInitialResponse(self):
        """
        Like L{test_invalidBase64EncodedResponse} but for the case of an
        initial response included with the C{AUTH} command.
        """
        loginArgs = []
        self.server.portal = self.portalFactory(loginArgs)

        self.server.dataReceived(b"EHLO\r\n")
        self.assertServerResponse(
            b"AUTH LOGIN x\r\n", [b"501 Syntax error in parameters or arguments"]
        )

        self.assertEqual(loginArgs, [])

    def test_unexpectedLoginFailure(self):
        """
        If the L{Deferred} returned by L{Portal.login} fires with an
        exception of any type other than L{UnauthorizedLogin}, the exception
        is logged and the client is informed that the authentication attempt
        has failed.
        """
        loginArgs = []
        self.server.portal = self.portalFactory(loginArgs)

        self.server.dataReceived(b"EHLO\r\n")
        self.transport.clear()

        self.assertServerResponse(
            b"AUTH LOGIN " + base64.b64encode(b"username").strip() + b"\r\n",
            [b"334 " + base64.b64encode(b"Password\0").strip()],
        )
        self.assertServerResponse(base64.b64encode(b"password").strip() + b"\r\n", [])

        d, credentials, mind, interfaces = loginArgs.pop()
        d.errback(RuntimeError("Something wrong with the server"))

        self.assertEqual(
            b"451 Requested action aborted: local error in processing\r\n",
            self.transport.value(),
        )

        self.assertEqual(len(self.flushLoggedErrors(RuntimeError)), 1)


class SMTPClientErrorTests(TestCase):
    """
    Tests for L{smtp.SMTPClientError}.
    """

    def test_str(self):
        """
        The string representation of a L{SMTPClientError} instance includes
        the response code and response string.
        """
        err = smtp.SMTPClientError(123, "some text")
        self.assertEqual(str(err), "123 some text")

    def test_strWithNegativeCode(self):
        """
        If the response code supplied to L{SMTPClientError} is negative, it
        is excluded from the string representation.
        """
        err = smtp.SMTPClientError(-1, b"foo bar")
        self.assertEqual(str(err), "foo bar")

    def test_strWithLog(self):
        """
        If a line log is supplied to L{SMTPClientError}, its contents are
        included in the string representation of the exception instance.
        """
        log = LineLog(10)
        log.append(b"testlog")
        log.append(b"secondline")
        err = smtp.SMTPClientError(100, "test error", log=log.str())
        self.assertEqual(str(err), "100 test error\n" "testlog\n" "secondline\n")


class SenderMixinSentMailTests(TestCase):
    """
    Tests for L{smtp.SenderMixin.sentMail}, used in particular by
    L{smtp.SMTPSenderFactory} and L{smtp.ESMTPSenderFactory}.
    """

    def test_onlyLogFailedAddresses(self):
        """
        L{smtp.SenderMixin.sentMail} adds only the addresses with failing
        SMTP response codes to the log passed to the factory's errback.
        """
        onDone = self.assertFailure(defer.Deferred(), smtp.SMTPDeliveryError)
        onDone.addCallback(
            lambda e: self.assertEqual(
                e.log, b"bob@example.com: 199 Error in sending.\n"
            )
        )

        clientFactory = smtp.SMTPSenderFactory(
            "source@address",
            "recipient@address",
            BytesIO(b"Message body"),
            onDone,
            retries=0,
            timeout=0.5,
        )

        client = clientFactory.buildProtocol(
            address.IPv4Address("TCP", "example.net", 25)
        )

        addresses = [
            (b"alice@example.com", 200, b"No errors here!"),
            (b"bob@example.com", 199, b"Error in sending."),
        ]
        client.sentMail(199, b"Test response", 1, addresses, client.log)

        return onDone


class ESMTPDowngradeTestCase(TestCase):
    """
    Tests for the ESMTP -> SMTP downgrade functionality in L{smtp.ESMTPClient}.
    """

    def setUp(self):
        self.clientProtocol = smtp.ESMTPClient(b"testpassword", None, b"testuser")

    def test_requireHELOFallbackOperates(self):
        """
        If both authentication and transport security are not required, and it
        is asked for, it will fall back to allowing HELO.
        """
        transport = StringTransport()
        self.clientProtocol.requireAuthentication = False
        self.clientProtocol.requireTransportSecurity = False
        self.clientProtocol.heloFallback = True
        self.clientProtocol.makeConnection(transport)

        self.clientProtocol.dataReceived(b"220 localhost\r\n")
        transport.clear()
        self.clientProtocol.dataReceived(b"500 not an esmtp server\r\n")
        self.assertEqual(b"HELO testuser\r\n", transport.value())

    def test_requireAuthFailsHELOFallback(self):
        """
        If authentication is required, and HELO fallback is on, HELO fallback
        must not be honoured, as authentication requires EHLO to succeed.
        """
        transport = StringTransport()
        self.clientProtocol.requireAuthentication = True
        self.clientProtocol.requireTransportSecurity = False
        self.clientProtocol.heloFallback = True
        self.clientProtocol.makeConnection(transport)

        self.clientProtocol.dataReceived(b"220 localhost\r\n")
        transport.clear()
        self.clientProtocol.dataReceived(b"500 not an esmtp server\r\n")
        self.assertEqual(b"QUIT\r\n", transport.value())

    def test_requireTLSFailsHELOFallback(self):
        """
        If TLS is required and the connection is insecure, HELO fallback must
        not be honoured, as STARTTLS requires EHLO to succeed.
        """
        transport = StringTransport()
        self.clientProtocol.requireAuthentication = False
        self.clientProtocol.requireTransportSecurity = True
        self.clientProtocol.heloFallback = True
        self.clientProtocol.makeConnection(transport)

        self.clientProtocol.dataReceived(b"220 localhost\r\n")
        transport.clear()
        self.clientProtocol.dataReceived(b"500 not an esmtp server\r\n")
        self.assertEqual(b"QUIT\r\n", transport.value())

    def test_requireTLSAndHELOFallbackSucceedsIfOverTLS(self):
        """
        If TLS is provided at the transport level, we can honour the HELO
        fallback if we're set to require TLS.
        """
        transport = StringTransport()
        directlyProvides(transport, interfaces.ISSLTransport)
        self.clientProtocol.requireAuthentication = False
        self.clientProtocol.requireTransportSecurity = True
        self.clientProtocol.heloFallback = True
        self.clientProtocol.makeConnection(transport)

        self.clientProtocol.dataReceived(b"220 localhost\r\n")
        transport.clear()
        self.clientProtocol.dataReceived(b"500 not an esmtp server\r\n")
        self.assertEqual(b"HELO testuser\r\n", transport.value())


class SSLTestCase(TestCase):
    """
    Tests for the TLS negotiation done by L{smtp.ESMTPClient}.
    """

    skip = sslSkip

    SERVER_GREETING = b"220 localhost NO UCE NO UBE NO RELAY PROBES ESMTP\r\n"
    EHLO_RESPONSE = b"250-localhost Hello 127.0.0.1, nice to meet you\r\n"

    def setUp(self):
        self.clientProtocol = smtp.ESMTPClient(
            b"testpassword", ClientTLSContext(), b"testuser"
        )
        self.clientProtocol.requireTransportSecurity = True
        self.clientProtocol.getMailFrom = lambda: "test@example.org"

    def _requireTransportSecurityOverSSLTest(self, capabilities):
        """
        Verify that when L{smtp.ESMTPClient} connects to a server over a
        transport providing L{ISSLTransport}, C{requireTransportSecurity} is
        C{True}, and it is presented with the given capabilities, it will try
        to send its mail and not first attempt to negotiate TLS using the
        I{STARTTLS} protocol action.

        @param capabilities: Bytes to include in the test server's capability
            response.  These must be formatted exactly as required by the
            protocol, including a line which ends the capability response.
        @type param: L{bytes}

        @raise: C{self.failureException} if the behavior of
            C{self.clientProtocol} is not as described.
        """
        transport = StringTransport()
        directlyProvides(transport, interfaces.ISSLTransport)
        self.clientProtocol.makeConnection(transport)

        # Get the handshake out of the way
        self.clientProtocol.dataReceived(self.SERVER_GREETING)
        transport.clear()

        # Tell the client about the server's capabilities
        self.clientProtocol.dataReceived(self.EHLO_RESPONSE + capabilities)

        # The client should now try to send a message - without first trying to
        # negotiate TLS, since the transport is already secure.
        self.assertEqual(b"MAIL FROM:<test@example.org>\r\n", transport.value())

    def test_requireTransportSecurityOverSSL(self):
        """
        When C{requireTransportSecurity} is C{True} and the client is connected
        over an SSL transport, mail may be delivered.
        """
        self._requireTransportSecurityOverSSLTest(b"250 AUTH LOGIN\r\n")

    def test_requireTransportSecurityTLSOffered(self):
        """
        When C{requireTransportSecurity} is C{True} and the client is connected
        over a non-SSL transport, if the server offers the I{STARTTLS}
        extension, it is used before mail is delivered.
        """
        transport = StringTransport()
        self.clientProtocol.makeConnection(transport)

        # Get the handshake out of the way
        self.clientProtocol.dataReceived(self.SERVER_GREETING)
        transport.clear()

        # Tell the client about the server's capabilities - including STARTTLS
        self.clientProtocol.dataReceived(
            self.EHLO_RESPONSE + b"250-AUTH LOGIN\r\n" b"250 STARTTLS\r\n"
        )

        # The client should try to start TLS before sending the message.
        self.assertEqual(b"STARTTLS\r\n", transport.value())

    def test_requireTransportSecurityTLSOfferedOverSSL(self):
        """
        When C{requireTransportSecurity} is C{True} and the client is connected
        over an SSL transport, if the server offers the I{STARTTLS}
        extension, it is not used before mail is delivered.
        """
        self._requireTransportSecurityOverSSLTest(
            b"250-AUTH LOGIN\r\n" b"250 STARTTLS\r\n"
        )

    def test_requireTransportSecurityTLSNotOffered(self):
        """
        When C{requireTransportSecurity} is C{True} and the client is connected
        over a non-SSL transport, if the server does not offer the I{STARTTLS}
        extension, mail is not delivered.
        """
        transport = StringTransport()
        self.clientProtocol.makeConnection(transport)

        # Get the handshake out of the way
        self.clientProtocol.dataReceived(self.SERVER_GREETING)
        transport.clear()

        # Tell the client about the server's capabilities - excluding STARTTLS
        self.clientProtocol.dataReceived(self.EHLO_RESPONSE + b"250 AUTH LOGIN\r\n")

        # The client give up
        self.assertEqual(b"QUIT\r\n", transport.value())

    def test_esmtpClientTlsModeDeprecationGet(self):
        """
        L{smtp.ESMTPClient.tlsMode} is deprecated.
        """
        val = self.clientProtocol.tlsMode
        del val
        warningsShown = self.flushWarnings(
            offendingFunctions=[self.test_esmtpClientTlsModeDeprecationGet]
        )
        self.assertEqual(len(warningsShown), 1)
        self.assertIdentical(warningsShown[0]["category"], DeprecationWarning)
        self.assertEqual(
            warningsShown[0]["message"],
            "tlsMode attribute of twisted.mail.smtp.ESMTPClient "
            "is deprecated since Twisted 13.0",
        )

    def test_esmtpClientTlsModeDeprecationGetAttributeError(self):
        """
        L{smtp.ESMTPClient.__getattr__} raises an attribute error for other
        attribute names which do not exist.
        """
        self.assertRaises(AttributeError, lambda: self.clientProtocol.doesNotExist)

    def test_esmtpClientTlsModeDeprecationSet(self):
        """
        L{smtp.ESMTPClient.tlsMode} is deprecated.
        """
        self.clientProtocol.tlsMode = False
        warningsShown = self.flushWarnings(
            offendingFunctions=[self.test_esmtpClientTlsModeDeprecationSet]
        )
        self.assertEqual(len(warningsShown), 1)
        self.assertIdentical(warningsShown[0]["category"], DeprecationWarning)
        self.assertEqual(
            warningsShown[0]["message"],
            "tlsMode attribute of twisted.mail.smtp.ESMTPClient "
            "is deprecated since Twisted 13.0",
        )


class AbortableStringTransport(StringTransport):
    """
    A version of L{StringTransport} that supports C{abortConnection}.
    """

    # This should be replaced by a common version in #6530.
    aborting = False

    def abortConnection(self):
        """
        A testable version of the C{ITCPTransport.abortConnection} method.

        Since this is a special case of closing the connection,
        C{loseConnection} is also called.
        """
        self.aborting = True
        self.loseConnection()


class SendmailTests(TestCase):
    """
    Tests for L{twisted.mail.smtp.sendmail}.
    """

    def test_defaultReactorIsGlobalReactor(self):
        """
        The default C{reactor} parameter of L{twisted.mail.smtp.sendmail} is
        L{twisted.internet.reactor}.
        """
        args, varArgs, keywords, defaults = inspect.getargspec(smtp.sendmail)
        self.assertEqual(reactor, defaults[2])

    def _honorsESMTPArguments(self, username, password):
        """
        L{twisted.mail.smtp.sendmail} creates the ESMTP factory with the ESMTP
        arguments.
        """
        reactor = MemoryReactor()
        smtp.sendmail(
            "localhost",
            "source@address",
            "recipient@address",
            b"message",
            reactor=reactor,
            username=username,
            password=password,
            requireTransportSecurity=True,
            requireAuthentication=True,
        )
        factory = reactor.tcpClients[0][2]
        self.assertEqual(factory._requireTransportSecurity, True)
        self.assertEqual(factory._requireAuthentication, True)
        self.assertEqual(factory.username, b"foo")
        self.assertEqual(factory.password, b"bar")

    def test_honorsESMTPArgumentsUnicodeUserPW(self):
        """
        L{twisted.mail.smtp.sendmail} should accept C{username} and C{password}
        which are L{unicode}.
        """
        return self._honorsESMTPArguments(username="foo", password="bar")

    def test_honorsESMTPArgumentsBytesUserPW(self):
        """
        L{twisted.mail.smtp.sendmail} should accept C{username} and C{password}
        which are L{bytes}.
        """
        return self._honorsESMTPArguments(username=b"foo", password=b"bar")

    def test_messageFilePassthrough(self):
        """
        L{twisted.mail.smtp.sendmail} will pass through the message untouched
        if it is a file-like object.
        """
        reactor = MemoryReactor()
        messageFile = BytesIO(b"File!")

        smtp.sendmail(
            "localhost",
            "source@address",
            "recipient@address",
            messageFile,
            reactor=reactor,
        )
        factory = reactor.tcpClients[0][2]
        self.assertIs(factory.file, messageFile)

    def test_messageStringMadeFile(self):
        """
        L{twisted.mail.smtp.sendmail} will turn non-file-like objects
        (eg. strings) into file-like objects before sending.
        """
        reactor = MemoryReactor()
        smtp.sendmail(
            "localhost",
            "source@address",
            "recipient@address",
            b"message",
            reactor=reactor,
        )
        factory = reactor.tcpClients[0][2]
        messageFile = factory.file
        messageFile.seek(0)
        self.assertEqual(messageFile.read(), b"message")

    def test_senderDomainName(self):
        """
        L{twisted.mail.smtp.sendmail} passes through the sender domain name, if
        provided.
        """
        reactor = MemoryReactor()
        smtp.sendmail(
            "localhost",
            "source@address",
            "recipient@address",
            b"message",
            reactor=reactor,
            senderDomainName="foo",
        )
        factory = reactor.tcpClients[0][2]
        self.assertEqual(factory.domain, b"foo")

    def test_cancelBeforeConnectionMade(self):
        """
        When a user cancels L{twisted.mail.smtp.sendmail} before the connection
        is made, the connection is closed by
        L{twisted.internet.interfaces.IConnector.disconnect}.
        """
        reactor = MemoryReactor()
        d = smtp.sendmail(
            "localhost",
            "source@address",
            "recipient@address",
            b"message",
            reactor=reactor,
        )
        d.cancel()
        self.assertEqual(reactor.connectors[0]._disconnected, True)
        failure = self.failureResultOf(d)
        failure.trap(defer.CancelledError)

    def test_cancelAfterConnectionMade(self):
        """
        When a user cancels L{twisted.mail.smtp.sendmail} after the connection
        is made, the connection is closed by
        L{twisted.internet.interfaces.ITransport.abortConnection}.
        """
        reactor = MemoryReactor()
        transport = AbortableStringTransport()
        d = smtp.sendmail(
            "localhost",
            "source@address",
            "recipient@address",
            b"message",
            reactor=reactor,
        )
        factory = reactor.tcpClients[0][2]
        p = factory.buildProtocol(None)
        p.makeConnection(transport)
        d.cancel()
        self.assertEqual(transport.aborting, True)
        self.assertEqual(transport.disconnecting, True)
        failure = self.failureResultOf(d)
        failure.trap(defer.CancelledError)
