# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.words.protocols.jabber.xmlstream}.
"""

from unittest import skipIf

from zope.interface.verify import verifyObject

from twisted.internet import defer, task
from twisted.internet.error import ConnectionLost
from twisted.internet.interfaces import IProtocolFactory
from twisted.python import failure
from twisted.test import proto_helpers
from twisted.trial import unittest
from twisted.words.protocols.jabber import error, ijabber, jid, xmlstream
from twisted.words.test.test_xmlstream import GenericXmlStreamFactoryTestsMixin
from twisted.words.xish import domish

try:
    from twisted.internet import ssl as _ssl
except ImportError:
    ssl = None
    skipWhenNoSSL = (True, "SSL not available")
else:
    ssl = _ssl
    skipWhenNoSSL = (False, "")
    from twisted.internet._sslverify import ClientTLSOptions
    from twisted.internet.ssl import CertificateOptions

NS_XMPP_TLS = "urn:ietf:params:xml:ns:xmpp-tls"


class HashPasswordTests(unittest.TestCase):
    """
    Tests for L{xmlstream.hashPassword}.
    """

    def test_basic(self):
        """
        The sid and secret are concatenated to calculate sha1 hex digest.
        """
        hash = xmlstream.hashPassword("12345", "secret")
        self.assertEqual("99567ee91b2c7cabf607f10cb9f4a3634fa820e0", hash)

    def test_sidNotUnicode(self):
        """
        The session identifier must be a unicode object.
        """
        self.assertRaises(TypeError, xmlstream.hashPassword, b"\xc2\xb92345", "secret")

    def test_passwordNotUnicode(self):
        """
        The password must be a unicode object.
        """
        self.assertRaises(TypeError, xmlstream.hashPassword, "12345", b"secr\xc3\xa9t")

    def test_unicodeSecret(self):
        """
        The concatenated sid and password must be encoded to UTF-8 before hashing.
        """
        hash = xmlstream.hashPassword("12345", "secr\u00e9t")
        self.assertEqual("659bf88d8f8e179081f7f3b4a8e7d224652d2853", hash)


class IQTests(unittest.TestCase):
    """
    Tests both IQ and the associated IIQResponseTracker callback.
    """

    def setUp(self):
        authenticator = xmlstream.ConnectAuthenticator("otherhost")
        authenticator.namespace = "testns"
        self.xmlstream = xmlstream.XmlStream(authenticator)
        self.clock = task.Clock()
        self.xmlstream._callLater = self.clock.callLater
        self.xmlstream.makeConnection(proto_helpers.StringTransport())
        self.xmlstream.dataReceived(
            "<stream:stream xmlns:stream='http://etherx.jabber.org/streams' "
            "xmlns='testns' from='otherhost' version='1.0'>"
        )
        self.iq = xmlstream.IQ(self.xmlstream, "get")

    def testBasic(self):
        self.assertEqual(self.iq["type"], "get")
        self.assertTrue(self.iq["id"])

    def testSend(self):
        self.xmlstream.transport.clear()
        self.iq.send()
        idBytes = self.iq["id"].encode("utf-8")
        self.assertIn(
            self.xmlstream.transport.value(),
            [
                b"<iq type='get' id='" + idBytes + b"'/>",
                b"<iq id='" + idBytes + b"' type='get'/>",
            ],
        )

    def testResultResponse(self):
        def cb(result):
            self.assertEqual(result["type"], "result")

        d = self.iq.send()
        d.addCallback(cb)

        xs = self.xmlstream
        xs.dataReceived("<iq type='result' id='%s'/>" % self.iq["id"])
        return d

    def testErrorResponse(self):
        d = self.iq.send()
        self.assertFailure(d, error.StanzaError)

        xs = self.xmlstream
        xs.dataReceived("<iq type='error' id='%s'/>" % self.iq["id"])
        return d

    def testNonTrackedResponse(self):
        """
        Test that untracked iq responses don't trigger any action.

        Untracked means that the id of the incoming response iq is not
        in the stream's C{iqDeferreds} dictionary.
        """
        xs = self.xmlstream
        xmlstream.upgradeWithIQResponseTracker(xs)

        # Make sure we aren't tracking any iq's.
        self.assertFalse(xs.iqDeferreds)

        # Set up a fallback handler that checks the stanza's handled attribute.
        # If that is set to True, the iq tracker claims to have handled the
        # response.
        def cb(iq):
            self.assertFalse(getattr(iq, "handled", False))

        xs.addObserver("/iq", cb, -1)

        # Receive an untracked iq response
        xs.dataReceived("<iq type='result' id='test'/>")

    def testCleanup(self):
        """
        Test if the deferred associated with an iq request is removed
        from the list kept in the L{XmlStream} object after it has
        been fired.
        """

        d = self.iq.send()
        xs = self.xmlstream
        xs.dataReceived("<iq type='result' id='%s'/>" % self.iq["id"])
        self.assertNotIn(self.iq["id"], xs.iqDeferreds)
        return d

    def testDisconnectCleanup(self):
        """
        Test if deferreds for iq's that haven't yet received a response
        have their errback called on stream disconnect.
        """

        d = self.iq.send()
        xs = self.xmlstream
        xs.connectionLost("Closed by peer")
        self.assertFailure(d, ConnectionLost)
        return d

    def testNoModifyingDict(self):
        """
        Test to make sure the errbacks cannot cause the iteration of the
        iqDeferreds to blow up in our face.
        """

        def eb(failure):
            d = xmlstream.IQ(self.xmlstream).send()
            d.addErrback(eb)

        d = self.iq.send()
        d.addErrback(eb)
        self.xmlstream.connectionLost("Closed by peer")
        return d

    def testRequestTimingOut(self):
        """
        Test that an iq request with a defined timeout times out.
        """
        self.iq.timeout = 60
        d = self.iq.send()
        self.assertFailure(d, xmlstream.TimeoutError)

        self.clock.pump([1, 60])
        self.assertFalse(self.clock.calls)
        self.assertFalse(self.xmlstream.iqDeferreds)
        return d

    def testRequestNotTimingOut(self):
        """
        Test that an iq request with a defined timeout does not time out
        when a response was received before the timeout period elapsed.
        """
        self.iq.timeout = 60
        d = self.iq.send()
        self.clock.callLater(
            1,
            self.xmlstream.dataReceived,
            "<iq type='result' id='%s'/>" % self.iq["id"],
        )
        self.clock.pump([1, 1])
        self.assertFalse(self.clock.calls)
        return d

    def testDisconnectTimeoutCancellation(self):
        """
        Test if timeouts for iq's that haven't yet received a response
        are cancelled on stream disconnect.
        """

        self.iq.timeout = 60
        d = self.iq.send()

        xs = self.xmlstream
        xs.connectionLost("Closed by peer")
        self.assertFailure(d, ConnectionLost)
        self.assertFalse(self.clock.calls)
        return d


class XmlStreamTests(unittest.TestCase):
    def onStreamStart(self, obj):
        self.gotStreamStart = True

    def onStreamEnd(self, obj):
        self.gotStreamEnd = True

    def onStreamError(self, obj):
        self.gotStreamError = True

    def setUp(self):
        """
        Set up XmlStream and several observers.
        """
        self.gotStreamStart = False
        self.gotStreamEnd = False
        self.gotStreamError = False
        xs = xmlstream.XmlStream(xmlstream.Authenticator())
        xs.addObserver("//event/stream/start", self.onStreamStart)
        xs.addObserver("//event/stream/end", self.onStreamEnd)
        xs.addObserver("//event/stream/error", self.onStreamError)
        xs.makeConnection(proto_helpers.StringTransportWithDisconnection())
        xs.transport.protocol = xs
        xs.namespace = "testns"
        xs.version = (1, 0)
        self.xmlstream = xs

    def test_sendHeaderBasic(self):
        """
        Basic test on the header sent by sendHeader.
        """
        xs = self.xmlstream
        xs.sendHeader()
        splitHeader = self.xmlstream.transport.value()[0:-1].split(b" ")
        self.assertIn(b"<stream:stream", splitHeader)
        self.assertIn(b"xmlns:stream='http://etherx.jabber.org/streams'", splitHeader)
        self.assertIn(b"xmlns='testns'", splitHeader)
        self.assertIn(b"version='1.0'", splitHeader)
        self.assertTrue(xs._headerSent)

    def test_sendHeaderAdditionalNamespaces(self):
        """
        Test for additional namespace declarations.
        """
        xs = self.xmlstream
        xs.prefixes["jabber:server:dialback"] = "db"
        xs.sendHeader()
        splitHeader = self.xmlstream.transport.value()[0:-1].split(b" ")
        self.assertIn(b"<stream:stream", splitHeader)
        self.assertIn(b"xmlns:stream='http://etherx.jabber.org/streams'", splitHeader)
        self.assertIn(b"xmlns:db='jabber:server:dialback'", splitHeader)
        self.assertIn(b"xmlns='testns'", splitHeader)
        self.assertIn(b"version='1.0'", splitHeader)
        self.assertTrue(xs._headerSent)

    def test_sendHeaderInitiating(self):
        """
        Test addressing when initiating a stream.
        """
        xs = self.xmlstream
        xs.thisEntity = jid.JID("thisHost")
        xs.otherEntity = jid.JID("otherHost")
        xs.initiating = True
        xs.sendHeader()
        splitHeader = xs.transport.value()[0:-1].split(b" ")
        self.assertIn(b"to='otherhost'", splitHeader)
        self.assertIn(b"from='thishost'", splitHeader)

    def test_sendHeaderReceiving(self):
        """
        Test addressing when receiving a stream.
        """
        xs = self.xmlstream
        xs.thisEntity = jid.JID("thisHost")
        xs.otherEntity = jid.JID("otherHost")
        xs.initiating = False
        xs.sid = "session01"
        xs.sendHeader()
        splitHeader = xs.transport.value()[0:-1].split(b" ")
        self.assertIn(b"to='otherhost'", splitHeader)
        self.assertIn(b"from='thishost'", splitHeader)
        self.assertIn(b"id='session01'", splitHeader)

    def test_receiveStreamError(self):
        """
        Test events when a stream error is received.
        """
        xs = self.xmlstream
        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.com' id='12345' version='1.0'>"
        )
        xs.dataReceived("<stream:error/>")
        self.assertTrue(self.gotStreamError)
        self.assertTrue(self.gotStreamEnd)

    def test_sendStreamErrorInitiating(self):
        """
        Test sendStreamError on an initiating xmlstream with a header sent.

        An error should be sent out and the connection lost.
        """
        xs = self.xmlstream
        xs.initiating = True
        xs.sendHeader()
        xs.transport.clear()
        xs.sendStreamError(error.StreamError("version-unsupported"))
        self.assertNotEqual(b"", xs.transport.value())
        self.assertTrue(self.gotStreamEnd)

    def test_sendStreamErrorInitiatingNoHeader(self):
        """
        Test sendStreamError on an initiating xmlstream without having sent a
        header.

        In this case, no header should be generated. Also, the error should
        not be sent out on the stream. Just closing the connection.
        """
        xs = self.xmlstream
        xs.initiating = True
        xs.transport.clear()
        xs.sendStreamError(error.StreamError("version-unsupported"))
        self.assertNot(xs._headerSent)
        self.assertEqual(b"", xs.transport.value())
        self.assertTrue(self.gotStreamEnd)

    def test_sendStreamErrorReceiving(self):
        """
        Test sendStreamError on a receiving xmlstream with a header sent.

        An error should be sent out and the connection lost.
        """
        xs = self.xmlstream
        xs.initiating = False
        xs.sendHeader()
        xs.transport.clear()
        xs.sendStreamError(error.StreamError("version-unsupported"))
        self.assertNotEqual(b"", xs.transport.value())
        self.assertTrue(self.gotStreamEnd)

    def test_sendStreamErrorReceivingNoHeader(self):
        """
        Test sendStreamError on a receiving xmlstream without having sent a
        header.

        In this case, a header should be generated. Then, the error should
        be sent out on the stream followed by closing the connection.
        """
        xs = self.xmlstream
        xs.initiating = False
        xs.transport.clear()
        xs.sendStreamError(error.StreamError("version-unsupported"))
        self.assertTrue(xs._headerSent)
        self.assertNotEqual(b"", xs.transport.value())
        self.assertTrue(self.gotStreamEnd)

    def test_reset(self):
        """
        Test resetting the XML stream to start a new layer.
        """
        xs = self.xmlstream
        xs.sendHeader()
        stream = xs.stream
        xs.reset()
        self.assertNotEqual(stream, xs.stream)
        self.assertNot(xs._headerSent)

    def test_send(self):
        """
        Test send with various types of objects.
        """
        xs = self.xmlstream
        xs.send("<presence/>")
        self.assertEqual(xs.transport.value(), b"<presence/>")

        xs.transport.clear()
        el = domish.Element(("testns", "presence"))
        xs.send(el)
        self.assertEqual(xs.transport.value(), b"<presence/>")

        xs.transport.clear()
        el = domish.Element(("http://etherx.jabber.org/streams", "features"))
        xs.send(el)
        self.assertEqual(xs.transport.value(), b"<stream:features/>")

    def test_authenticator(self):
        """
        Test that the associated authenticator is correctly called.
        """
        connectionMadeCalls = []
        streamStartedCalls = []
        associateWithStreamCalls = []

        class TestAuthenticator:
            def connectionMade(self):
                connectionMadeCalls.append(None)

            def streamStarted(self, rootElement):
                streamStartedCalls.append(rootElement)

            def associateWithStream(self, xs):
                associateWithStreamCalls.append(xs)

        a = TestAuthenticator()
        xs = xmlstream.XmlStream(a)
        self.assertEqual([xs], associateWithStreamCalls)
        xs.connectionMade()
        self.assertEqual([None], connectionMadeCalls)
        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.com' id='12345'>"
        )
        self.assertEqual(1, len(streamStartedCalls))
        xs.reset()
        self.assertEqual([None], connectionMadeCalls)


class TestError(Exception):
    pass


class AuthenticatorTests(unittest.TestCase):
    def setUp(self):
        self.authenticator = xmlstream.Authenticator()
        self.xmlstream = xmlstream.XmlStream(self.authenticator)

    def test_streamStart(self):
        """
        Test streamStart to fill the appropriate attributes from the
        stream header.
        """
        xs = self.xmlstream
        xs.makeConnection(proto_helpers.StringTransport())
        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.org' to='example.com' id='12345' "
            "version='1.0'>"
        )
        self.assertEqual((1, 0), xs.version)
        self.assertIdentical(None, xs.sid)
        self.assertEqual("invalid", xs.namespace)
        self.assertIdentical(None, xs.otherEntity)
        self.assertEqual(None, xs.thisEntity)

    def test_streamStartLegacy(self):
        """
        Test streamStart to fill the appropriate attributes from the
        stream header for a pre-XMPP-1.0 header.
        """
        xs = self.xmlstream
        xs.makeConnection(proto_helpers.StringTransport())
        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.com' id='12345'>"
        )
        self.assertEqual((0, 0), xs.version)

    def test_streamBadVersionOneDigit(self):
        """
        Test streamStart to fill the appropriate attributes from the
        stream header for a version with only one digit.
        """
        xs = self.xmlstream
        xs.makeConnection(proto_helpers.StringTransport())
        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.com' id='12345' version='1'>"
        )
        self.assertEqual((0, 0), xs.version)

    def test_streamBadVersionNoNumber(self):
        """
        Test streamStart to fill the appropriate attributes from the
        stream header for a malformed version.
        """
        xs = self.xmlstream
        xs.makeConnection(proto_helpers.StringTransport())
        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.com' id='12345' version='blah'>"
        )
        self.assertEqual((0, 0), xs.version)


class ConnectAuthenticatorTests(unittest.TestCase):
    def setUp(self):
        self.gotAuthenticated = False
        self.initFailure = None
        self.authenticator = xmlstream.ConnectAuthenticator("otherHost")
        self.xmlstream = xmlstream.XmlStream(self.authenticator)
        self.xmlstream.addObserver("//event/stream/authd", self.onAuthenticated)
        self.xmlstream.addObserver("//event/xmpp/initfailed", self.onInitFailed)

    def onAuthenticated(self, obj):
        self.gotAuthenticated = True

    def onInitFailed(self, failure):
        self.initFailure = failure

    def testSucces(self):
        """
        Test successful completion of an initialization step.
        """

        class Initializer:
            def initialize(self):
                pass

        init = Initializer()
        self.xmlstream.initializers = [init]

        self.authenticator.initializeStream()
        self.assertEqual([], self.xmlstream.initializers)
        self.assertTrue(self.gotAuthenticated)

    def testFailure(self):
        """
        Test failure of an initialization step.
        """

        class Initializer:
            def initialize(self):
                raise TestError

        init = Initializer()
        self.xmlstream.initializers = [init]

        self.authenticator.initializeStream()
        self.assertEqual([init], self.xmlstream.initializers)
        self.assertFalse(self.gotAuthenticated)
        self.assertNotIdentical(None, self.initFailure)
        self.assertTrue(self.initFailure.check(TestError))

    def test_streamStart(self):
        """
        Test streamStart to fill the appropriate attributes from the
        stream header.
        """
        self.authenticator.namespace = "testns"
        xs = self.xmlstream
        xs.makeConnection(proto_helpers.StringTransport())
        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.com' to='example.org' id='12345' "
            "version='1.0'>"
        )
        self.assertEqual((1, 0), xs.version)
        self.assertEqual("12345", xs.sid)
        self.assertEqual("testns", xs.namespace)
        self.assertEqual("example.com", xs.otherEntity.host)
        self.assertIdentical(None, xs.thisEntity)
        self.assertNot(self.gotAuthenticated)
        xs.dataReceived(
            "<stream:features>" "<test xmlns='testns'/>" "</stream:features>"
        )
        self.assertIn(("testns", "test"), xs.features)
        self.assertTrue(self.gotAuthenticated)


class ListenAuthenticatorTests(unittest.TestCase):
    """
    Tests for L{xmlstream.ListenAuthenticator}
    """

    def setUp(self):
        self.authenticator = xmlstream.ListenAuthenticator()
        self.xmlstream = xmlstream.XmlStream(self.authenticator)

    def test_streamStart(self):
        """
        Test streamStart to fill the appropriate attributes from the
        stream header.
        """
        xs = self.xmlstream
        xs.makeConnection(proto_helpers.StringTransport())
        self.assertIdentical(None, xs.sid)
        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.org' to='example.com' id='12345' "
            "version='1.0'>"
        )
        self.assertEqual((1, 0), xs.version)
        self.assertNotIdentical(None, xs.sid)
        self.assertNotEqual("12345", xs.sid)
        self.assertEqual("jabber:client", xs.namespace)
        self.assertIdentical(None, xs.otherEntity)
        self.assertEqual("example.com", xs.thisEntity.host)

    def test_streamStartUnicodeSessionID(self):
        """
        The generated session id must be a unicode object.
        """
        xs = self.xmlstream
        xs.makeConnection(proto_helpers.StringTransport())
        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.org' to='example.com' id='12345' "
            "version='1.0'>"
        )
        self.assertIsInstance(xs.sid, str)


class TLSInitiatingInitializerTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.done = []

        self.savedSSL = xmlstream.ssl

        self.authenticator = xmlstream.ConnectAuthenticator("example.com")
        self.xmlstream = xmlstream.XmlStream(self.authenticator)
        self.xmlstream.send = self.output.append
        self.xmlstream.connectionMade()
        self.xmlstream.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.com' id='12345' version='1.0'>"
        )
        self.init = xmlstream.TLSInitiatingInitializer(self.xmlstream)

    def tearDown(self):
        xmlstream.ssl = self.savedSSL

    def test_initRequired(self):
        """
        Passing required sets the instance variable.
        """
        self.init = xmlstream.TLSInitiatingInitializer(self.xmlstream, required=True)
        self.assertTrue(self.init.required)

    @skipIf(*skipWhenNoSSL)
    def test_wantedSupported(self):
        """
        When TLS is wanted and SSL available, StartTLS is initiated.
        """
        self.xmlstream.transport = proto_helpers.StringTransport()
        self.xmlstream.transport.startTLS = lambda ctx: self.done.append("TLS")
        self.xmlstream.reset = lambda: self.done.append("reset")
        self.xmlstream.sendHeader = lambda: self.done.append("header")

        d = self.init.start()
        d.addCallback(self.assertEqual, xmlstream.Reset)
        self.assertEqual(2, len(self.output))
        starttls = self.output[1]
        self.assertEqual("starttls", starttls.name)
        self.assertEqual(NS_XMPP_TLS, starttls.uri)
        self.xmlstream.dataReceived("<proceed xmlns='%s'/>" % NS_XMPP_TLS)
        self.assertEqual(["TLS", "reset", "header"], self.done)

        return d

    @skipIf(*skipWhenNoSSL)
    def test_certificateVerify(self):
        """
        The server certificate will be verified.
        """

        def fakeStartTLS(contextFactory):
            self.assertIsInstance(contextFactory, ClientTLSOptions)
            self.assertEqual(contextFactory._hostname, "example.com")
            self.done.append("TLS")

        self.xmlstream.transport = proto_helpers.StringTransport()
        self.xmlstream.transport.startTLS = fakeStartTLS
        self.xmlstream.reset = lambda: self.done.append("reset")
        self.xmlstream.sendHeader = lambda: self.done.append("header")

        d = self.init.start()
        self.xmlstream.dataReceived("<proceed xmlns='%s'/>" % NS_XMPP_TLS)
        self.assertEqual(["TLS", "reset", "header"], self.done)
        return d

    @skipIf(*skipWhenNoSSL)
    def test_certificateVerifyContext(self):
        """
        A custom contextFactory is passed through to startTLS.
        """
        ctx = CertificateOptions()
        self.init = xmlstream.TLSInitiatingInitializer(
            self.xmlstream, configurationForTLS=ctx
        )

        self.init.contextFactory = ctx

        def fakeStartTLS(contextFactory):
            self.assertIs(ctx, contextFactory)
            self.done.append("TLS")

        self.xmlstream.transport = proto_helpers.StringTransport()
        self.xmlstream.transport.startTLS = fakeStartTLS
        self.xmlstream.reset = lambda: self.done.append("reset")
        self.xmlstream.sendHeader = lambda: self.done.append("header")

        d = self.init.start()
        self.xmlstream.dataReceived("<proceed xmlns='%s'/>" % NS_XMPP_TLS)
        self.assertEqual(["TLS", "reset", "header"], self.done)
        return d

    def test_wantedNotSupportedNotRequired(self):
        """
        No StartTLS is initiated when wanted, not required, SSL not available.
        """
        xmlstream.ssl = None
        self.init.required = False

        d = self.init.start()
        d.addCallback(self.assertEqual, None)
        self.assertEqual(1, len(self.output))

        return d

    def test_wantedNotSupportedRequired(self):
        """
        TLSNotSupported is raised when TLS is required but not available.
        """
        xmlstream.ssl = None
        self.init.required = True

        d = self.init.start()
        self.assertFailure(d, xmlstream.TLSNotSupported)
        self.assertEqual(1, len(self.output))

        return d

    def test_notWantedRequired(self):
        """
        TLSRequired is raised when TLS is not wanted, but required by server.
        """
        tls = domish.Element(("urn:ietf:params:xml:ns:xmpp-tls", "starttls"))
        tls.addElement("required")
        self.xmlstream.features = {(tls.uri, tls.name): tls}
        self.init.wanted = False

        d = self.init.start()
        self.assertEqual(1, len(self.output))
        self.assertFailure(d, xmlstream.TLSRequired)

        return d

    def test_notWantedNotRequired(self):
        """
        No StartTLS is initiated when not wanted and not required.
        """
        tls = domish.Element(("urn:ietf:params:xml:ns:xmpp-tls", "starttls"))
        self.xmlstream.features = {(tls.uri, tls.name): tls}
        self.init.wanted = False
        self.init.required = False

        d = self.init.start()
        d.addCallback(self.assertEqual, None)
        self.assertEqual(1, len(self.output))
        return d

    def test_failed(self):
        """
        TLSFailed is raised when the server responds with a failure.
        """
        # Pretend that ssl is supported, it isn't actually used when the
        # server starts out with a failure in response to our initial
        # C{starttls} stanza.
        xmlstream.ssl = 1

        d = self.init.start()
        self.assertFailure(d, xmlstream.TLSFailed)
        self.xmlstream.dataReceived("<failure xmlns='%s'/>" % NS_XMPP_TLS)
        return d


class TestFeatureInitializer(xmlstream.BaseFeatureInitiatingInitializer):
    feature = ("testns", "test")

    def start(self):
        return defer.succeed(None)


class BaseFeatureInitiatingInitializerTests(unittest.TestCase):
    def setUp(self):
        self.xmlstream = xmlstream.XmlStream(xmlstream.Authenticator())
        self.init = TestFeatureInitializer(self.xmlstream)

    def testAdvertized(self):
        """
        Test that an advertized feature results in successful initialization.
        """
        self.xmlstream.features = {self.init.feature: domish.Element(self.init.feature)}
        return self.init.initialize()

    def testNotAdvertizedRequired(self):
        """
        Test that when the feature is not advertized, but required by the
        initializer, an exception is raised.
        """
        self.init.required = True
        self.assertRaises(xmlstream.FeatureNotAdvertized, self.init.initialize)

    def testNotAdvertizedNotRequired(self):
        """
        Test that when the feature is not advertized, and not required by the
        initializer, the initializer silently succeeds.
        """
        self.init.required = False
        self.assertIdentical(None, self.init.initialize())


class ToResponseTests(unittest.TestCase):
    def test_toResponse(self):
        """
        Test that a response stanza is generated with addressing swapped.
        """
        stanza = domish.Element(("jabber:client", "iq"))
        stanza["type"] = "get"
        stanza["to"] = "user1@example.com"
        stanza["from"] = "user2@example.com/resource"
        stanza["id"] = "stanza1"
        response = xmlstream.toResponse(stanza, "result")
        self.assertNotIdentical(stanza, response)
        self.assertEqual(response["from"], "user1@example.com")
        self.assertEqual(response["to"], "user2@example.com/resource")
        self.assertEqual(response["type"], "result")
        self.assertEqual(response["id"], "stanza1")

    def test_toResponseNoFrom(self):
        """
        Test that a response is generated from a stanza without a from address.
        """
        stanza = domish.Element(("jabber:client", "iq"))
        stanza["type"] = "get"
        stanza["to"] = "user1@example.com"
        response = xmlstream.toResponse(stanza)
        self.assertEqual(response["from"], "user1@example.com")
        self.assertFalse(response.hasAttribute("to"))

    def test_toResponseNoTo(self):
        """
        Test that a response is generated from a stanza without a to address.
        """
        stanza = domish.Element(("jabber:client", "iq"))
        stanza["type"] = "get"
        stanza["from"] = "user2@example.com/resource"
        response = xmlstream.toResponse(stanza)
        self.assertFalse(response.hasAttribute("from"))
        self.assertEqual(response["to"], "user2@example.com/resource")

    def test_toResponseNoAddressing(self):
        """
        Test that a response is generated from a stanza without any addressing.
        """
        stanza = domish.Element(("jabber:client", "message"))
        stanza["type"] = "chat"
        response = xmlstream.toResponse(stanza)
        self.assertFalse(response.hasAttribute("to"))
        self.assertFalse(response.hasAttribute("from"))

    def test_noID(self):
        """
        Test that a proper response is generated without id attribute.
        """
        stanza = domish.Element(("jabber:client", "message"))
        response = xmlstream.toResponse(stanza)
        self.assertFalse(response.hasAttribute("id"))

    def test_noType(self):
        """
        Test that a proper response is generated without type attribute.
        """
        stanza = domish.Element(("jabber:client", "message"))
        response = xmlstream.toResponse(stanza)
        self.assertFalse(response.hasAttribute("type"))


class DummyFactory:
    """
    Dummy XmlStream factory that only registers bootstrap observers.
    """

    def __init__(self):
        self.callbacks = {}

    def addBootstrap(self, event, callback):
        self.callbacks[event] = callback


class DummyXMPPHandler(xmlstream.XMPPHandler):
    """
    Dummy XMPP subprotocol handler to count the methods are called on it.
    """

    def __init__(self):
        self.doneMade = 0
        self.doneInitialized = 0
        self.doneLost = 0

    def makeConnection(self, xs):
        self.connectionMade()

    def connectionMade(self):
        self.doneMade += 1

    def connectionInitialized(self):
        self.doneInitialized += 1

    def connectionLost(self, reason):
        self.doneLost += 1


class FailureReasonXMPPHandler(xmlstream.XMPPHandler):
    """
    Dummy handler specifically for failure Reason tests.
    """

    def __init__(self):
        self.gotFailureReason = False

    def connectionLost(self, reason):
        if isinstance(reason, failure.Failure):
            self.gotFailureReason = True


class XMPPHandlerTests(unittest.TestCase):
    """
    Tests for L{xmlstream.XMPPHandler}.
    """

    def test_interface(self):
        """
        L{xmlstream.XMPPHandler} implements L{ijabber.IXMPPHandler}.
        """
        verifyObject(ijabber.IXMPPHandler, xmlstream.XMPPHandler())

    def test_send(self):
        """
        Test that data is passed on for sending by the stream manager.
        """

        class DummyStreamManager:
            def __init__(self):
                self.outlist = []

            def send(self, data):
                self.outlist.append(data)

        handler = xmlstream.XMPPHandler()
        handler.parent = DummyStreamManager()
        handler.send("<presence/>")
        self.assertEqual(["<presence/>"], handler.parent.outlist)

    def test_makeConnection(self):
        """
        Test that makeConnection saves the XML stream and calls connectionMade.
        """

        class TestXMPPHandler(xmlstream.XMPPHandler):
            def connectionMade(self):
                self.doneMade = True

        handler = TestXMPPHandler()
        xs = xmlstream.XmlStream(xmlstream.Authenticator())
        handler.makeConnection(xs)
        self.assertTrue(handler.doneMade)
        self.assertIdentical(xs, handler.xmlstream)

    def test_connectionLost(self):
        """
        Test that connectionLost forgets the XML stream.
        """
        handler = xmlstream.XMPPHandler()
        xs = xmlstream.XmlStream(xmlstream.Authenticator())
        handler.makeConnection(xs)
        handler.connectionLost(Exception())
        self.assertIdentical(None, handler.xmlstream)


class XMPPHandlerCollectionTests(unittest.TestCase):
    """
    Tests for L{xmlstream.XMPPHandlerCollection}.
    """

    def setUp(self):
        self.collection = xmlstream.XMPPHandlerCollection()

    def test_interface(self):
        """
        L{xmlstream.StreamManager} implements L{ijabber.IXMPPHandlerCollection}.
        """
        verifyObject(ijabber.IXMPPHandlerCollection, self.collection)

    def test_addHandler(self):
        """
        Test the addition of a protocol handler.
        """
        handler = DummyXMPPHandler()
        handler.setHandlerParent(self.collection)
        self.assertIn(handler, self.collection)
        self.assertIdentical(self.collection, handler.parent)

    def test_removeHandler(self):
        """
        Test removal of a protocol handler.
        """
        handler = DummyXMPPHandler()
        handler.setHandlerParent(self.collection)
        handler.disownHandlerParent(self.collection)
        self.assertNotIn(handler, self.collection)
        self.assertIdentical(None, handler.parent)


class StreamManagerTests(unittest.TestCase):
    """
    Tests for L{xmlstream.StreamManager}.
    """

    def setUp(self):
        factory = DummyFactory()
        self.streamManager = xmlstream.StreamManager(factory)

    def test_basic(self):
        """
        Test correct initialization and setup of factory observers.
        """
        sm = self.streamManager
        self.assertIdentical(None, sm.xmlstream)
        self.assertEqual([], sm.handlers)
        self.assertEqual(
            sm._connected, sm.factory.callbacks["//event/stream/connected"]
        )
        self.assertEqual(sm._authd, sm.factory.callbacks["//event/stream/authd"])
        self.assertEqual(sm._disconnected, sm.factory.callbacks["//event/stream/end"])
        self.assertEqual(
            sm.initializationFailed, sm.factory.callbacks["//event/xmpp/initfailed"]
        )

    def test_connected(self):
        """
        Test that protocol handlers have their connectionMade method called
        when the XML stream is connected.
        """
        sm = self.streamManager
        handler = DummyXMPPHandler()
        handler.setHandlerParent(sm)
        xs = xmlstream.XmlStream(xmlstream.Authenticator())
        sm._connected(xs)
        self.assertEqual(1, handler.doneMade)
        self.assertEqual(0, handler.doneInitialized)
        self.assertEqual(0, handler.doneLost)

    def test_connectedLogTrafficFalse(self):
        """
        Test raw data functions unset when logTraffic is set to False.
        """
        sm = self.streamManager
        handler = DummyXMPPHandler()
        handler.setHandlerParent(sm)
        xs = xmlstream.XmlStream(xmlstream.Authenticator())
        sm._connected(xs)
        self.assertIdentical(None, xs.rawDataInFn)
        self.assertIdentical(None, xs.rawDataOutFn)

    def test_connectedLogTrafficTrue(self):
        """
        Test raw data functions set when logTraffic is set to True.
        """
        sm = self.streamManager
        sm.logTraffic = True
        handler = DummyXMPPHandler()
        handler.setHandlerParent(sm)
        xs = xmlstream.XmlStream(xmlstream.Authenticator())
        sm._connected(xs)
        self.assertNotIdentical(None, xs.rawDataInFn)
        self.assertNotIdentical(None, xs.rawDataOutFn)

    def test_authd(self):
        """
        Test that protocol handlers have their connectionInitialized method
        called when the XML stream is initialized.
        """
        sm = self.streamManager
        handler = DummyXMPPHandler()
        handler.setHandlerParent(sm)
        xs = xmlstream.XmlStream(xmlstream.Authenticator())
        sm._authd(xs)
        self.assertEqual(0, handler.doneMade)
        self.assertEqual(1, handler.doneInitialized)
        self.assertEqual(0, handler.doneLost)

    def test_disconnected(self):
        """
        Test that protocol handlers have their connectionLost method
        called when the XML stream is disconnected.
        """
        sm = self.streamManager
        handler = DummyXMPPHandler()
        handler.setHandlerParent(sm)
        xs = xmlstream.XmlStream(xmlstream.Authenticator())
        sm._disconnected(xs)
        self.assertEqual(0, handler.doneMade)
        self.assertEqual(0, handler.doneInitialized)
        self.assertEqual(1, handler.doneLost)

    def test_disconnectedReason(self):
        """
        A L{STREAM_END_EVENT} results in L{StreamManager} firing the handlers
        L{connectionLost} methods, passing a L{failure.Failure} reason.
        """
        sm = self.streamManager
        handler = FailureReasonXMPPHandler()
        handler.setHandlerParent(sm)
        sm._disconnected(failure.Failure(Exception("no reason")))
        self.assertEqual(True, handler.gotFailureReason)

    def test_addHandler(self):
        """
        Test the addition of a protocol handler while not connected.
        """
        sm = self.streamManager
        handler = DummyXMPPHandler()
        handler.setHandlerParent(sm)

        self.assertEqual(0, handler.doneMade)
        self.assertEqual(0, handler.doneInitialized)
        self.assertEqual(0, handler.doneLost)

    def test_addHandlerInitialized(self):
        """
        Test the addition of a protocol handler after the stream
        have been initialized.

        Make sure that the handler will have the connected stream
        passed via C{makeConnection} and have C{connectionInitialized}
        called.
        """
        sm = self.streamManager
        xs = xmlstream.XmlStream(xmlstream.Authenticator())
        sm._connected(xs)
        sm._authd(xs)
        handler = DummyXMPPHandler()
        handler.setHandlerParent(sm)

        self.assertEqual(1, handler.doneMade)
        self.assertEqual(1, handler.doneInitialized)
        self.assertEqual(0, handler.doneLost)

    def test_sendInitialized(self):
        """
        Test send when the stream has been initialized.

        The data should be sent directly over the XML stream.
        """
        factory = xmlstream.XmlStreamFactory(xmlstream.Authenticator())
        sm = xmlstream.StreamManager(factory)
        xs = factory.buildProtocol(None)
        xs.transport = proto_helpers.StringTransport()
        xs.connectionMade()
        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.com' id='12345'>"
        )
        xs.dispatch(xs, "//event/stream/authd")
        sm.send("<presence/>")
        self.assertEqual(b"<presence/>", xs.transport.value())

    def test_sendNotConnected(self):
        """
        Test send when there is no established XML stream.

        The data should be cached until an XML stream has been established and
        initialized.
        """
        factory = xmlstream.XmlStreamFactory(xmlstream.Authenticator())
        sm = xmlstream.StreamManager(factory)
        handler = DummyXMPPHandler()
        sm.addHandler(handler)

        xs = factory.buildProtocol(None)
        xs.transport = proto_helpers.StringTransport()
        sm.send("<presence/>")
        self.assertEqual(b"", xs.transport.value())
        self.assertEqual("<presence/>", sm._packetQueue[0])

        xs.connectionMade()
        self.assertEqual(b"", xs.transport.value())
        self.assertEqual("<presence/>", sm._packetQueue[0])

        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.com' id='12345'>"
        )
        xs.dispatch(xs, "//event/stream/authd")

        self.assertEqual(b"<presence/>", xs.transport.value())
        self.assertFalse(sm._packetQueue)

    def test_sendNotInitialized(self):
        """
        Test send when the stream is connected but not yet initialized.

        The data should be cached until the XML stream has been initialized.
        """
        factory = xmlstream.XmlStreamFactory(xmlstream.Authenticator())
        sm = xmlstream.StreamManager(factory)
        xs = factory.buildProtocol(None)
        xs.transport = proto_helpers.StringTransport()
        xs.connectionMade()
        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.com' id='12345'>"
        )
        sm.send("<presence/>")
        self.assertEqual(b"", xs.transport.value())
        self.assertEqual("<presence/>", sm._packetQueue[0])

    def test_sendDisconnected(self):
        """
        Test send after XML stream disconnection.

        The data should be cached until a new XML stream has been established
        and initialized.
        """
        factory = xmlstream.XmlStreamFactory(xmlstream.Authenticator())
        sm = xmlstream.StreamManager(factory)
        handler = DummyXMPPHandler()
        sm.addHandler(handler)

        xs = factory.buildProtocol(None)
        xs.connectionMade()
        xs.transport = proto_helpers.StringTransport()
        xs.connectionLost(None)

        sm.send("<presence/>")
        self.assertEqual(b"", xs.transport.value())
        self.assertEqual("<presence/>", sm._packetQueue[0])


class XmlStreamServerFactoryTests(GenericXmlStreamFactoryTestsMixin):
    """
    Tests for L{xmlstream.XmlStreamServerFactory}.
    """

    def setUp(self):
        """
        Set up a server factory with an authenticator factory function.
        """

        class TestAuthenticator:
            def __init__(self):
                self.xmlstreams = []

            def associateWithStream(self, xs):
                self.xmlstreams.append(xs)

        def authenticatorFactory():
            return TestAuthenticator()

        self.factory = xmlstream.XmlStreamServerFactory(authenticatorFactory)

    def test_interface(self):
        """
        L{XmlStreamServerFactory} is a L{Factory}.
        """
        verifyObject(IProtocolFactory, self.factory)

    def test_buildProtocolAuthenticatorInstantiation(self):
        """
        The authenticator factory should be used to instantiate the
        authenticator and pass it to the protocol.

        The default protocol, L{XmlStream} stores the authenticator it is
        passed, and calls its C{associateWithStream} method. so we use that to
        check whether our authenticator factory is used and the protocol
        instance gets an authenticator.
        """
        xs = self.factory.buildProtocol(None)
        self.assertEqual([xs], xs.authenticator.xmlstreams)

    def test_buildProtocolXmlStream(self):
        """
        The protocol factory creates Jabber XML Stream protocols by default.
        """
        xs = self.factory.buildProtocol(None)
        self.assertIsInstance(xs, xmlstream.XmlStream)

    def test_buildProtocolTwice(self):
        """
        Subsequent calls to buildProtocol should result in different instances
        of the protocol, as well as their authenticators.
        """
        xs1 = self.factory.buildProtocol(None)
        xs2 = self.factory.buildProtocol(None)
        self.assertNotIdentical(xs1, xs2)
        self.assertNotIdentical(xs1.authenticator, xs2.authenticator)
