# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.words.protocols.jabber.component}
"""
from hashlib import sha1

from zope.interface.verify import verifyObject

from twisted.python import failure
from twisted.trial import unittest
from twisted.words.protocols.jabber import component, ijabber, xmlstream
from twisted.words.protocols.jabber.jid import JID
from twisted.words.xish import domish
from twisted.words.xish.utility import XmlPipe


class DummyTransport:
    def __init__(self, list):
        self.list = list

    def write(self, bytes):
        self.list.append(bytes)


class ComponentInitiatingInitializerTests(unittest.TestCase):
    def setUp(self):
        self.output = []

        self.authenticator = xmlstream.Authenticator()
        self.authenticator.password = "secret"
        self.xmlstream = xmlstream.XmlStream(self.authenticator)
        self.xmlstream.namespace = "test:component"
        self.xmlstream.send = self.output.append
        self.xmlstream.connectionMade()
        self.xmlstream.dataReceived(
            "<stream:stream xmlns='test:component' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "from='example.com' id='12345' version='1.0'>"
        )
        self.xmlstream.sid = "12345"
        self.init = component.ComponentInitiatingInitializer(self.xmlstream)

    def testHandshake(self):
        """
        Test basic operations of component handshake.
        """

        d = self.init.initialize()

        # the initializer should have sent the handshake request

        handshake = self.output[-1]
        self.assertEqual("handshake", handshake.name)
        self.assertEqual("test:component", handshake.uri)
        self.assertEqual(sha1(b"12345" + b"secret").hexdigest(), str(handshake))

        # successful authentication

        handshake.children = []
        self.xmlstream.dataReceived(handshake.toXml())

        return d


class ComponentAuthTests(unittest.TestCase):
    def authPassed(self, stream):
        self.authComplete = True

    def testAuth(self):
        self.authComplete = False
        outlist = []

        ca = component.ConnectComponentAuthenticator("cjid", "secret")
        xs = xmlstream.XmlStream(ca)
        xs.transport = DummyTransport(outlist)

        xs.addObserver(xmlstream.STREAM_AUTHD_EVENT, self.authPassed)

        # Go...
        xs.connectionMade()
        xs.dataReceived(
            b"<stream:stream xmlns='jabber:component:accept' xmlns:stream='http://etherx.jabber.org/streams' from='cjid' id='12345'>"
        )

        # Calculate what we expect the handshake value to be
        hv = sha1(b"12345" + b"secret").hexdigest().encode("ascii")

        self.assertEqual(outlist[1], b"<handshake>" + hv + b"</handshake>")

        xs.dataReceived("<handshake/>")

        self.assertEqual(self.authComplete, True)


class ServiceTests(unittest.TestCase):
    """
    Tests for L{component.Service}.
    """

    def test_interface(self):
        """
        L{component.Service} implements L{ijabber.IService}.
        """
        service = component.Service()
        verifyObject(ijabber.IService, service)


class JabberServiceHarness(component.Service):
    def __init__(self):
        self.componentConnectedFlag = False
        self.componentDisconnectedFlag = False
        self.transportConnectedFlag = False

    def componentConnected(self, xmlstream):
        self.componentConnectedFlag = True

    def componentDisconnected(self):
        self.componentDisconnectedFlag = True

    def transportConnected(self, xmlstream):
        self.transportConnectedFlag = True


class JabberServiceManagerTests(unittest.TestCase):
    def testSM(self):
        # Setup service manager and test harnes
        sm = component.ServiceManager("foo", "password")
        svc = JabberServiceHarness()
        svc.setServiceParent(sm)

        # Create a write list
        wlist = []

        # Setup a XmlStream
        xs = sm.getFactory().buildProtocol(None)
        xs.transport = self
        xs.transport.write = wlist.append

        # Indicate that it's connected
        xs.connectionMade()

        # Ensure the test service harness got notified
        self.assertEqual(True, svc.transportConnectedFlag)

        # Jump ahead and pretend like the stream got auth'd
        xs.dispatch(xs, xmlstream.STREAM_AUTHD_EVENT)

        # Ensure the test service harness got notified
        self.assertEqual(True, svc.componentConnectedFlag)

        # Pretend to drop the connection
        xs.connectionLost(None)

        # Ensure the test service harness got notified
        self.assertEqual(True, svc.componentDisconnectedFlag)


class RouterTests(unittest.TestCase):
    """
    Tests for L{component.Router}.
    """

    def test_addRoute(self):
        """
        Test route registration and routing on incoming stanzas.
        """
        router = component.Router()
        routed = []
        router.route = lambda element: routed.append(element)

        pipe = XmlPipe()
        router.addRoute("example.org", pipe.sink)
        self.assertEqual(1, len(router.routes))
        self.assertEqual(pipe.sink, router.routes["example.org"])

        element = domish.Element(("testns", "test"))
        pipe.source.send(element)
        self.assertEqual([element], routed)

    def test_route(self):
        """
        Test routing of a message.
        """
        component1 = XmlPipe()
        component2 = XmlPipe()
        router = component.Router()
        router.addRoute("component1.example.org", component1.sink)
        router.addRoute("component2.example.org", component2.sink)

        outgoing = []
        component2.source.addObserver("/*", lambda element: outgoing.append(element))
        stanza = domish.Element((None, "presence"))
        stanza["from"] = "component1.example.org"
        stanza["to"] = "component2.example.org"
        component1.source.send(stanza)
        self.assertEqual([stanza], outgoing)

    def test_routeDefault(self):
        """
        Test routing of a message using the default route.

        The default route is the one with L{None} as its key in the
        routing table. It is taken when there is no more specific route
        in the routing table that matches the stanza's destination.
        """
        component1 = XmlPipe()
        s2s = XmlPipe()
        router = component.Router()
        router.addRoute("component1.example.org", component1.sink)
        router.addRoute(None, s2s.sink)

        outgoing = []
        s2s.source.addObserver("/*", lambda element: outgoing.append(element))
        stanza = domish.Element((None, "presence"))
        stanza["from"] = "component1.example.org"
        stanza["to"] = "example.com"
        component1.source.send(stanza)
        self.assertEqual([stanza], outgoing)


class ListenComponentAuthenticatorTests(unittest.TestCase):
    """
    Tests for L{component.ListenComponentAuthenticator}.
    """

    def setUp(self):
        self.output = []
        authenticator = component.ListenComponentAuthenticator("secret")
        self.xmlstream = xmlstream.XmlStream(authenticator)
        self.xmlstream.send = self.output.append

    def loseConnection(self):
        """
        Stub loseConnection because we are a transport.
        """
        self.xmlstream.connectionLost("no reason")

    def test_streamStarted(self):
        """
        The received stream header should set several attributes.
        """
        observers = []

        def addOnetimeObserver(event, observerfn):
            observers.append((event, observerfn))

        xs = self.xmlstream
        xs.addOnetimeObserver = addOnetimeObserver

        xs.makeConnection(self)
        self.assertIdentical(None, xs.sid)
        self.assertFalse(xs._headerSent)

        xs.dataReceived(
            "<stream:stream xmlns='jabber:component:accept' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "to='component.example.org'>"
        )
        self.assertEqual((0, 0), xs.version)
        self.assertNotIdentical(None, xs.sid)
        self.assertTrue(xs._headerSent)
        self.assertEqual(("/*", xs.authenticator.onElement), observers[-1])

    def test_streamStartedWrongNamespace(self):
        """
        The received stream header should have a correct namespace.
        """
        streamErrors = []

        xs = self.xmlstream
        xs.sendStreamError = streamErrors.append
        xs.makeConnection(self)
        xs.dataReceived(
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams' "
            "to='component.example.org'>"
        )
        self.assertEqual(1, len(streamErrors))
        self.assertEqual("invalid-namespace", streamErrors[-1].condition)

    def test_streamStartedNoTo(self):
        """
        The received stream header should have a 'to' attribute.
        """
        streamErrors = []

        xs = self.xmlstream
        xs.sendStreamError = streamErrors.append
        xs.makeConnection(self)
        xs.dataReceived(
            "<stream:stream xmlns='jabber:component:accept' "
            "xmlns:stream='http://etherx.jabber.org/streams'>"
        )
        self.assertEqual(1, len(streamErrors))
        self.assertEqual("improper-addressing", streamErrors[-1].condition)

    def test_onElement(self):
        """
        We expect a handshake element with a hash.
        """
        handshakes = []

        xs = self.xmlstream
        xs.authenticator.onHandshake = handshakes.append

        handshake = domish.Element(("jabber:component:accept", "handshake"))
        handshake.addContent("1234")
        xs.authenticator.onElement(handshake)
        self.assertEqual("1234", handshakes[-1])

    def test_onElementNotHandshake(self):
        """
        Reject elements that are not handshakes
        """
        handshakes = []
        streamErrors = []

        xs = self.xmlstream
        xs.authenticator.onHandshake = handshakes.append
        xs.sendStreamError = streamErrors.append

        element = domish.Element(("jabber:component:accept", "message"))
        xs.authenticator.onElement(element)
        self.assertFalse(handshakes)
        self.assertEqual("not-authorized", streamErrors[-1].condition)

    def test_onHandshake(self):
        """
        Receiving a handshake matching the secret authenticates the stream.
        """
        authd = []

        def authenticated(xs):
            authd.append(xs)

        xs = self.xmlstream
        xs.addOnetimeObserver(xmlstream.STREAM_AUTHD_EVENT, authenticated)
        xs.sid = "1234"
        theHash = "32532c0f7dbf1253c095b18b18e36d38d94c1256"
        xs.authenticator.onHandshake(theHash)
        self.assertEqual("<handshake/>", self.output[-1])
        self.assertEqual(1, len(authd))

    def test_onHandshakeWrongHash(self):
        """
        Receiving a bad handshake should yield a stream error.
        """
        streamErrors = []
        authd = []

        def authenticated(xs):
            authd.append(xs)

        xs = self.xmlstream
        xs.addOnetimeObserver(xmlstream.STREAM_AUTHD_EVENT, authenticated)
        xs.sendStreamError = streamErrors.append

        xs.sid = "1234"
        theHash = "1234"
        xs.authenticator.onHandshake(theHash)
        self.assertEqual("not-authorized", streamErrors[-1].condition)
        self.assertEqual(0, len(authd))


class XMPPComponentServerFactoryTests(unittest.TestCase):
    """
    Tests for L{component.XMPPComponentServerFactory}.
    """

    def setUp(self):
        self.router = component.Router()
        self.factory = component.XMPPComponentServerFactory(self.router, "secret")
        self.xmlstream = self.factory.buildProtocol(None)
        self.xmlstream.thisEntity = JID("component.example.org")

    def test_makeConnection(self):
        """
        A new connection increases the stream serial count. No logs by default.
        """
        self.xmlstream.dispatch(self.xmlstream, xmlstream.STREAM_CONNECTED_EVENT)
        self.assertEqual(0, self.xmlstream.serial)
        self.assertEqual(1, self.factory.serial)
        self.assertIdentical(None, self.xmlstream.rawDataInFn)
        self.assertIdentical(None, self.xmlstream.rawDataOutFn)

    def test_makeConnectionLogTraffic(self):
        """
        Setting logTraffic should set up raw data loggers.
        """
        self.factory.logTraffic = True
        self.xmlstream.dispatch(self.xmlstream, xmlstream.STREAM_CONNECTED_EVENT)
        self.assertNotIdentical(None, self.xmlstream.rawDataInFn)
        self.assertNotIdentical(None, self.xmlstream.rawDataOutFn)

    def test_onError(self):
        """
        An observer for stream errors should trigger onError to log it.
        """
        self.xmlstream.dispatch(self.xmlstream, xmlstream.STREAM_CONNECTED_EVENT)

        class TestError(Exception):
            pass

        reason = failure.Failure(TestError())
        self.xmlstream.dispatch(reason, xmlstream.STREAM_ERROR_EVENT)
        self.assertEqual(1, len(self.flushLoggedErrors(TestError)))

    def test_connectionInitialized(self):
        """
        Make sure a new stream is added to the routing table.
        """
        self.xmlstream.dispatch(self.xmlstream, xmlstream.STREAM_AUTHD_EVENT)
        self.assertIn("component.example.org", self.router.routes)
        self.assertIdentical(
            self.xmlstream, self.router.routes["component.example.org"]
        )

    def test_connectionLost(self):
        """
        Make sure a stream is removed from the routing table on disconnect.
        """
        self.xmlstream.dispatch(self.xmlstream, xmlstream.STREAM_AUTHD_EVENT)
        self.xmlstream.dispatch(None, xmlstream.STREAM_END_EVENT)
        self.assertNotIn("component.example.org", self.router.routes)
