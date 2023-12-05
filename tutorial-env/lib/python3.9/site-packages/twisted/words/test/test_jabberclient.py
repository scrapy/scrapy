# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.words.protocols.jabber.client}
"""


from hashlib import sha1
from unittest import skipIf

from twisted.internet import defer
from twisted.trial import unittest
from twisted.words.protocols.jabber import client, error, jid, xmlstream
from twisted.words.protocols.jabber.sasl import SASLInitiatingInitializer
from twisted.words.xish import utility

try:
    from twisted.internet import ssl
except ImportError:
    ssl = None  # type: ignore[assignment]
    skipWhenNoSSL = (True, "SSL not available")
else:
    skipWhenNoSSL = (False, "")

IQ_AUTH_GET = '/iq[@type="get"]/query[@xmlns="jabber:iq:auth"]'
IQ_AUTH_SET = '/iq[@type="set"]/query[@xmlns="jabber:iq:auth"]'
NS_BIND = "urn:ietf:params:xml:ns:xmpp-bind"
IQ_BIND_SET = '/iq[@type="set"]/bind[@xmlns="%s"]' % NS_BIND
NS_SESSION = "urn:ietf:params:xml:ns:xmpp-session"
IQ_SESSION_SET = '/iq[@type="set"]/session[@xmlns="%s"]' % NS_SESSION


class CheckVersionInitializerTests(unittest.TestCase):
    def setUp(self):
        a = xmlstream.Authenticator()
        xs = xmlstream.XmlStream(a)
        self.init = client.CheckVersionInitializer(xs)

    def testSupported(self):
        """
        Test supported version number 1.0
        """
        self.init.xmlstream.version = (1, 0)
        self.init.initialize()

    def testNotSupported(self):
        """
        Test unsupported version number 0.0, and check exception.
        """
        self.init.xmlstream.version = (0, 0)
        exc = self.assertRaises(error.StreamError, self.init.initialize)
        self.assertEqual("unsupported-version", exc.condition)


class InitiatingInitializerHarness:
    """
    Testing harness for interacting with XML stream initializers.

    This sets up an L{utility.XmlPipe} to create a communication channel between
    the initializer and the stubbed receiving entity. It features a sink and
    source side that both act similarly to a real L{xmlstream.XmlStream}. The
    sink is augmented with an authenticator to which initializers can be added.

    The harness also provides some utility methods to work with event observers
    and deferreds.
    """

    def setUp(self):
        self.output = []
        self.pipe = utility.XmlPipe()
        self.xmlstream = self.pipe.sink
        self.authenticator = xmlstream.ConnectAuthenticator("example.org")
        self.xmlstream.authenticator = self.authenticator

    def waitFor(self, event, handler):
        """
        Observe an output event, returning a deferred.

        The returned deferred will be fired when the given event has been
        observed on the source end of the L{XmlPipe} tied to the protocol
        under test. The handler is added as the first callback.

        @param event: The event to be observed. See
            L{utility.EventDispatcher.addOnetimeObserver}.
        @param handler: The handler to be called with the observed event object.
        @rtype: L{defer.Deferred}.
        """
        d = defer.Deferred()
        d.addCallback(handler)
        self.pipe.source.addOnetimeObserver(event, d.callback)
        return d


class IQAuthInitializerTests(InitiatingInitializerHarness, unittest.TestCase):
    """
    Tests for L{client.IQAuthInitializer}.
    """

    def setUp(self):
        super().setUp()
        self.init = client.IQAuthInitializer(self.xmlstream)
        self.authenticator.jid = jid.JID("user@example.com/resource")
        self.authenticator.password = "secret"

    def testPlainText(self):
        """
        Test plain-text authentication.

        Act as a server supporting plain-text authentication and expect the
        C{password} field to be filled with the password. Then act as if
        authentication succeeds.
        """

        def onAuthGet(iq):
            """
            Called when the initializer sent a query for authentication methods.

            The response informs the client that plain-text authentication
            is supported.
            """

            # Create server response
            response = xmlstream.toResponse(iq, "result")
            response.addElement(("jabber:iq:auth", "query"))
            response.query.addElement("username")
            response.query.addElement("password")
            response.query.addElement("resource")

            # Set up an observer for the next request we expect.
            d = self.waitFor(IQ_AUTH_SET, onAuthSet)

            # Send server response
            self.pipe.source.send(response)

            return d

        def onAuthSet(iq):
            """
            Called when the initializer sent the authentication request.

            The server checks the credentials and responds with an empty result
            signalling success.
            """
            self.assertEqual("user", str(iq.query.username))
            self.assertEqual("secret", str(iq.query.password))
            self.assertEqual("resource", str(iq.query.resource))

            # Send server response
            response = xmlstream.toResponse(iq, "result")
            self.pipe.source.send(response)

        # Set up an observer for the request for authentication fields
        d1 = self.waitFor(IQ_AUTH_GET, onAuthGet)

        # Start the initializer
        d2 = self.init.initialize()
        return defer.gatherResults([d1, d2])

    def testDigest(self):
        """
        Test digest authentication.

        Act as a server supporting digest authentication and expect the
        C{digest} field to be filled with a sha1 digest of the concatenated
        stream session identifier and password. Then act as if authentication
        succeeds.
        """

        def onAuthGet(iq):
            """
            Called when the initializer sent a query for authentication methods.

            The response informs the client that digest authentication is
            supported.
            """

            # Create server response
            response = xmlstream.toResponse(iq, "result")
            response.addElement(("jabber:iq:auth", "query"))
            response.query.addElement("username")
            response.query.addElement("digest")
            response.query.addElement("resource")

            # Set up an observer for the next request we expect.
            d = self.waitFor(IQ_AUTH_SET, onAuthSet)

            # Send server response
            self.pipe.source.send(response)

            return d

        def onAuthSet(iq):
            """
            Called when the initializer sent the authentication request.

            The server checks the credentials and responds with an empty result
            signalling success.
            """
            self.assertEqual("user", str(iq.query.username))
            self.assertEqual(sha1(b"12345secret").hexdigest(), str(iq.query.digest))
            self.assertEqual("resource", str(iq.query.resource))

            # Send server response
            response = xmlstream.toResponse(iq, "result")
            self.pipe.source.send(response)

        # Digest authentication relies on the stream session identifier. Set it.
        self.xmlstream.sid = "12345"

        # Set up an observer for the request for authentication fields
        d1 = self.waitFor(IQ_AUTH_GET, onAuthGet)

        # Start the initializer
        d2 = self.init.initialize()

        return defer.gatherResults([d1, d2])

    def testFailRequestFields(self):
        """
        Test initializer failure of request for fields for authentication.
        """

        def onAuthGet(iq):
            """
            Called when the initializer sent a query for authentication methods.

            The server responds that the client is not authorized to authenticate.
            """
            response = error.StanzaError("not-authorized").toResponse(iq)
            self.pipe.source.send(response)

        # Set up an observer for the request for authentication fields
        d1 = self.waitFor(IQ_AUTH_GET, onAuthGet)

        # Start the initializer
        d2 = self.init.initialize()

        # The initialized should fail with a stanza error.
        self.assertFailure(d2, error.StanzaError)

        return defer.gatherResults([d1, d2])

    def testFailAuth(self):
        """
        Test initializer failure to authenticate.
        """

        def onAuthGet(iq):
            """
            Called when the initializer sent a query for authentication methods.

            The response informs the client that plain-text authentication
            is supported.
            """

            # Send server response
            response = xmlstream.toResponse(iq, "result")
            response.addElement(("jabber:iq:auth", "query"))
            response.query.addElement("username")
            response.query.addElement("password")
            response.query.addElement("resource")

            # Set up an observer for the next request we expect.
            d = self.waitFor(IQ_AUTH_SET, onAuthSet)

            # Send server response
            self.pipe.source.send(response)

            return d

        def onAuthSet(iq):
            """
            Called when the initializer sent the authentication request.

            The server checks the credentials and responds with a not-authorized
            stanza error.
            """
            response = error.StanzaError("not-authorized").toResponse(iq)
            self.pipe.source.send(response)

        # Set up an observer for the request for authentication fields
        d1 = self.waitFor(IQ_AUTH_GET, onAuthGet)

        # Start the initializer
        d2 = self.init.initialize()

        # The initializer should fail with a stanza error.
        self.assertFailure(d2, error.StanzaError)

        return defer.gatherResults([d1, d2])


class BindInitializerTests(InitiatingInitializerHarness, unittest.TestCase):
    """
    Tests for L{client.BindInitializer}.
    """

    def setUp(self):
        super().setUp()
        self.init = client.BindInitializer(self.xmlstream)
        self.authenticator.jid = jid.JID("user@example.com/resource")

    def testBasic(self):
        """
        Set up a stream, and act as if resource binding succeeds.
        """

        def onBind(iq):
            response = xmlstream.toResponse(iq, "result")
            response.addElement((NS_BIND, "bind"))
            response.bind.addElement("jid", content="user@example.com/other resource")
            self.pipe.source.send(response)

        def cb(result):
            self.assertEqual(
                jid.JID("user@example.com/other resource"), self.authenticator.jid
            )

        d1 = self.waitFor(IQ_BIND_SET, onBind)
        d2 = self.init.start()
        d2.addCallback(cb)
        return defer.gatherResults([d1, d2])

    def testFailure(self):
        """
        Set up a stream, and act as if resource binding fails.
        """

        def onBind(iq):
            response = error.StanzaError("conflict").toResponse(iq)
            self.pipe.source.send(response)

        d1 = self.waitFor(IQ_BIND_SET, onBind)
        d2 = self.init.start()
        self.assertFailure(d2, error.StanzaError)
        return defer.gatherResults([d1, d2])


class SessionInitializerTests(InitiatingInitializerHarness, unittest.TestCase):
    """
    Tests for L{client.SessionInitializer}.
    """

    def setUp(self):
        super().setUp()
        self.init = client.SessionInitializer(self.xmlstream)

    def testSuccess(self):
        """
        Set up a stream, and act as if session establishment succeeds.
        """

        def onSession(iq):
            response = xmlstream.toResponse(iq, "result")
            self.pipe.source.send(response)

        d1 = self.waitFor(IQ_SESSION_SET, onSession)
        d2 = self.init.start()
        return defer.gatherResults([d1, d2])

    def testFailure(self):
        """
        Set up a stream, and act as if session establishment fails.
        """

        def onSession(iq):
            response = error.StanzaError("forbidden").toResponse(iq)
            self.pipe.source.send(response)

        d1 = self.waitFor(IQ_SESSION_SET, onSession)
        d2 = self.init.start()
        self.assertFailure(d2, error.StanzaError)
        return defer.gatherResults([d1, d2])


class BasicAuthenticatorTests(unittest.TestCase):
    """
    Test for both BasicAuthenticator and basicClientFactory.
    """

    def test_basic(self):
        """
        Authenticator and stream are properly constructed by the factory.

        The L{xmlstream.XmlStream} protocol created by the factory has the new
        L{client.BasicAuthenticator} instance in its C{authenticator}
        attribute.  It is set up with C{jid} and C{password} as passed to the
        factory, C{otherHost} taken from the client JID. The stream futher has
        two initializers, for TLS and authentication, of which the first has
        its C{required} attribute set to C{True}.
        """
        self.client_jid = jid.JID("user@example.com/resource")

        # Get an XmlStream instance. Note that it gets initialized with the
        # XMPPAuthenticator (that has its associateWithXmlStream called) that
        # is in turn initialized with the arguments to the factory.
        xs = client.basicClientFactory(self.client_jid, "secret").buildProtocol(None)

        # test authenticator's instance variables
        self.assertEqual("example.com", xs.authenticator.otherHost)
        self.assertEqual(self.client_jid, xs.authenticator.jid)
        self.assertEqual("secret", xs.authenticator.password)

        # test list of initializers
        tls, auth = xs.initializers

        self.assertIsInstance(tls, xmlstream.TLSInitiatingInitializer)
        self.assertIsInstance(auth, client.IQAuthInitializer)

        self.assertFalse(tls.required)


class XMPPAuthenticatorTests(unittest.TestCase):
    """
    Test for both XMPPAuthenticator and XMPPClientFactory.
    """

    def test_basic(self):
        """
        Test basic operations.

        Setup an XMPPClientFactory, which sets up an XMPPAuthenticator, and let
        it produce a protocol instance. Then inspect the instance variables of
        the authenticator and XML stream objects.
        """
        self.client_jid = jid.JID("user@example.com/resource")

        # Get an XmlStream instance. Note that it gets initialized with the
        # XMPPAuthenticator (that has its associateWithXmlStream called) that
        # is in turn initialized with the arguments to the factory.
        xs = client.XMPPClientFactory(self.client_jid, "secret").buildProtocol(None)

        # test authenticator's instance variables
        self.assertEqual("example.com", xs.authenticator.otherHost)
        self.assertEqual(self.client_jid, xs.authenticator.jid)
        self.assertEqual("secret", xs.authenticator.password)

        # test list of initializers
        version, tls, sasl, bind, session = xs.initializers

        self.assertIsInstance(tls, xmlstream.TLSInitiatingInitializer)
        self.assertIsInstance(sasl, SASLInitiatingInitializer)
        self.assertIsInstance(bind, client.BindInitializer)
        self.assertIsInstance(session, client.SessionInitializer)

        self.assertTrue(tls.required)
        self.assertTrue(sasl.required)
        self.assertTrue(bind.required)
        self.assertFalse(session.required)

    @skipIf(*skipWhenNoSSL)
    def test_tlsConfiguration(self):
        """
        A TLS configuration is passed to the TLS initializer.
        """
        configs = []

        def init(self, xs, required=True, configurationForTLS=None):
            configs.append(configurationForTLS)

        self.client_jid = jid.JID("user@example.com/resource")

        # Get an XmlStream instance. Note that it gets initialized with the
        # XMPPAuthenticator (that has its associateWithXmlStream called) that
        # is in turn initialized with the arguments to the factory.
        configurationForTLS = ssl.CertificateOptions()
        factory = client.XMPPClientFactory(
            self.client_jid, "secret", configurationForTLS=configurationForTLS
        )
        self.patch(xmlstream.TLSInitiatingInitializer, "__init__", init)
        xs = factory.buildProtocol(None)

        # test list of initializers
        version, tls, sasl, bind, session = xs.initializers

        self.assertIsInstance(tls, xmlstream.TLSInitiatingInitializer)
        self.assertIs(configurationForTLS, configs[0])
