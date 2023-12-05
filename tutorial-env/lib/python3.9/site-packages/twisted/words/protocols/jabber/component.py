# -*- test-case-name: twisted.words.test.test_jabbercomponent -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
External server-side components.

Most Jabber server implementations allow for add-on components that act as a
separate entity on the Jabber network, but use the server-to-server
functionality of a regular Jabber IM server. These so-called 'external
components' are connected to the Jabber server using the Jabber Component
Protocol as defined in U{JEP-0114<http://www.jabber.org/jeps/jep-0114.html>}.

This module allows for writing external server-side component by assigning one
or more services implementing L{ijabber.IService} up to L{ServiceManager}. The
ServiceManager connects to the Jabber server and is responsible for the
corresponding XML stream.
"""

from zope.interface import implementer

from twisted.application import service
from twisted.internet import defer
from twisted.python import log
from twisted.words.protocols.jabber import error, ijabber, jstrports, xmlstream
from twisted.words.protocols.jabber.jid import internJID as JID
from twisted.words.xish import domish

NS_COMPONENT_ACCEPT = "jabber:component:accept"


def componentFactory(componentid, password):
    """
    XML stream factory for external server-side components.

    @param componentid: JID of the component.
    @type componentid: L{unicode}
    @param password: password used to authenticate to the server.
    @type password: C{str}
    """
    a = ConnectComponentAuthenticator(componentid, password)
    return xmlstream.XmlStreamFactory(a)


class ComponentInitiatingInitializer:
    """
    External server-side component authentication initializer for the
    initiating entity.

    @ivar xmlstream: XML stream between server and component.
    @type xmlstream: L{xmlstream.XmlStream}
    """

    def __init__(self, xs):
        self.xmlstream = xs
        self._deferred = None

    def initialize(self):
        xs = self.xmlstream
        hs = domish.Element((self.xmlstream.namespace, "handshake"))
        digest = xmlstream.hashPassword(xs.sid, xs.authenticator.password)
        hs.addContent(str(digest))

        # Setup observer to watch for handshake result
        xs.addOnetimeObserver("/handshake", self._cbHandshake)
        xs.send(hs)
        self._deferred = defer.Deferred()
        return self._deferred

    def _cbHandshake(self, _):
        # we have successfully shaken hands and can now consider this
        # entity to represent the component JID.
        self.xmlstream.thisEntity = self.xmlstream.otherEntity
        self._deferred.callback(None)


class ConnectComponentAuthenticator(xmlstream.ConnectAuthenticator):
    """
    Authenticator to permit an XmlStream to authenticate against a Jabber
    server as an external component (where the Authenticator is initiating the
    stream).
    """

    namespace = NS_COMPONENT_ACCEPT

    def __init__(self, componentjid, password):
        """
        @type componentjid: C{str}
        @param componentjid: Jabber ID that this component wishes to bind to.

        @type password: C{str}
        @param password: Password/secret this component uses to authenticate.
        """
        # Note that we are sending 'to' our desired component JID.
        xmlstream.ConnectAuthenticator.__init__(self, componentjid)
        self.password = password

    def associateWithStream(self, xs):
        xs.version = (0, 0)
        xmlstream.ConnectAuthenticator.associateWithStream(self, xs)

        xs.initializers = [ComponentInitiatingInitializer(xs)]


class ListenComponentAuthenticator(xmlstream.ListenAuthenticator):
    """
    Authenticator for accepting components.

    @since: 8.2
    @ivar secret: The shared secret used to authorized incoming component
                  connections.
    @type secret: C{unicode}.
    """

    namespace = NS_COMPONENT_ACCEPT

    def __init__(self, secret):
        self.secret = secret
        xmlstream.ListenAuthenticator.__init__(self)

    def associateWithStream(self, xs):
        """
        Associate the authenticator with a stream.

        This sets the stream's version to 0.0, because the XEP-0114 component
        protocol was not designed for XMPP 1.0.
        """
        xs.version = (0, 0)
        xmlstream.ListenAuthenticator.associateWithStream(self, xs)

    def streamStarted(self, rootElement):
        """
        Called by the stream when it has started.

        This examines the default namespace of the incoming stream and whether
        there is a requested hostname for the component. Then it generates a
        stream identifier, sends a response header and adds an observer for
        the first incoming element, triggering L{onElement}.
        """

        xmlstream.ListenAuthenticator.streamStarted(self, rootElement)

        if rootElement.defaultUri != self.namespace:
            exc = error.StreamError("invalid-namespace")
            self.xmlstream.sendStreamError(exc)
            return

        # self.xmlstream.thisEntity is set to the address the component
        # wants to assume.
        if not self.xmlstream.thisEntity:
            exc = error.StreamError("improper-addressing")
            self.xmlstream.sendStreamError(exc)
            return

        self.xmlstream.sendHeader()
        self.xmlstream.addOnetimeObserver("/*", self.onElement)

    def onElement(self, element):
        """
        Called on incoming XML Stanzas.

        The very first element received should be a request for handshake.
        Otherwise, the stream is dropped with a 'not-authorized' error. If a
        handshake request was received, the hash is extracted and passed to
        L{onHandshake}.
        """
        if (element.uri, element.name) == (self.namespace, "handshake"):
            self.onHandshake(str(element))
        else:
            exc = error.StreamError("not-authorized")
            self.xmlstream.sendStreamError(exc)

    def onHandshake(self, handshake):
        """
        Called upon receiving the handshake request.

        This checks that the given hash in C{handshake} is equal to a
        calculated hash, responding with a handshake reply or a stream error.
        If the handshake was ok, the stream is authorized, and  XML Stanzas may
        be exchanged.
        """
        calculatedHash = xmlstream.hashPassword(self.xmlstream.sid, str(self.secret))
        if handshake != calculatedHash:
            exc = error.StreamError("not-authorized", text="Invalid hash")
            self.xmlstream.sendStreamError(exc)
        else:
            self.xmlstream.send("<handshake/>")
            self.xmlstream.dispatch(self.xmlstream, xmlstream.STREAM_AUTHD_EVENT)


@implementer(ijabber.IService)
class Service(service.Service):
    """
    External server-side component service.
    """

    def componentConnected(self, xs):
        pass

    def componentDisconnected(self):
        pass

    def transportConnected(self, xs):
        pass

    def send(self, obj):
        """
        Send data over service parent's XML stream.

        @note: L{ServiceManager} maintains a queue for data sent using this
        method when there is no current established XML stream. This data is
        then sent as soon as a new stream has been established and initialized.
        Subsequently, L{componentConnected} will be called again. If this
        queueing is not desired, use C{send} on the XmlStream object (passed to
        L{componentConnected}) directly.

        @param obj: data to be sent over the XML stream. This is usually an
        object providing L{domish.IElement}, or serialized XML. See
        L{xmlstream.XmlStream} for details.
        """

        self.parent.send(obj)


class ServiceManager(service.MultiService):
    """
    Business logic for a managed component connection to a Jabber router.

    This service maintains a single connection to a Jabber router and provides
    facilities for packet routing and transmission. Business logic modules are
    services implementing L{ijabber.IService} (like subclasses of L{Service}),
    and added as sub-service.
    """

    def __init__(self, jid, password):
        service.MultiService.__init__(self)

        # Setup defaults
        self.jabberId = jid
        self.xmlstream = None

        # Internal buffer of packets
        self._packetQueue = []

        # Setup the xmlstream factory
        self._xsFactory = componentFactory(self.jabberId, password)

        # Register some lambda functions to keep the self.xmlstream var up to
        # date
        self._xsFactory.addBootstrap(xmlstream.STREAM_CONNECTED_EVENT, self._connected)
        self._xsFactory.addBootstrap(xmlstream.STREAM_AUTHD_EVENT, self._authd)
        self._xsFactory.addBootstrap(xmlstream.STREAM_END_EVENT, self._disconnected)

        # Map addBootstrap and removeBootstrap to the underlying factory -- is
        # this right? I have no clue...but it'll work for now, until i can
        # think about it more.
        self.addBootstrap = self._xsFactory.addBootstrap
        self.removeBootstrap = self._xsFactory.removeBootstrap

    def getFactory(self):
        return self._xsFactory

    def _connected(self, xs):
        self.xmlstream = xs
        for c in self:
            if ijabber.IService.providedBy(c):
                c.transportConnected(xs)

    def _authd(self, xs):
        # Flush all pending packets
        for p in self._packetQueue:
            self.xmlstream.send(p)
        self._packetQueue = []

        # Notify all child services which implement the IService interface
        for c in self:
            if ijabber.IService.providedBy(c):
                c.componentConnected(xs)

    def _disconnected(self, _):
        self.xmlstream = None

        # Notify all child services which implement
        # the IService interface
        for c in self:
            if ijabber.IService.providedBy(c):
                c.componentDisconnected()

    def send(self, obj):
        """
        Send data over the XML stream.

        When there is no established XML stream, the data is queued and sent
        out when a new XML stream has been established and initialized.

        @param obj: data to be sent over the XML stream. This is usually an
        object providing L{domish.IElement}, or serialized XML. See
        L{xmlstream.XmlStream} for details.
        """

        if self.xmlstream != None:
            self.xmlstream.send(obj)
        else:
            self._packetQueue.append(obj)


def buildServiceManager(jid, password, strport):
    """
    Constructs a pre-built L{ServiceManager}, using the specified strport
    string.
    """

    svc = ServiceManager(jid, password)
    client_svc = jstrports.client(strport, svc.getFactory())
    client_svc.setServiceParent(svc)
    return svc


class Router:
    """
    XMPP Server's Router.

    A router connects the different components of the XMPP service and routes
    messages between them based on the given routing table.

    Connected components are trusted to have correct addressing in the
    stanzas they offer for routing.

    A route destination of L{None} adds a default route. Traffic for which no
    specific route exists, will be routed to this default route.

    @since: 8.2
    @ivar routes: Routes based on the host part of JIDs. Maps host names to the
                  L{EventDispatcher<utility.EventDispatcher>}s that should
                  receive the traffic. A key of L{None} means the default
                  route.
    @type routes: C{dict}
    """

    def __init__(self):
        self.routes = {}

    def addRoute(self, destination, xs):
        """
        Add a new route.

        The passed XML Stream C{xs} will have an observer for all stanzas
        added to route its outgoing traffic. In turn, traffic for
        C{destination} will be passed to this stream.

        @param destination: Destination of the route to be added as a host name
                            or L{None} for the default route.
        @type destination: C{str} or L{None}.
        @param xs: XML Stream to register the route for.
        @type xs: L{EventDispatcher<utility.EventDispatcher>}.
        """
        self.routes[destination] = xs
        xs.addObserver("/*", self.route)

    def removeRoute(self, destination, xs):
        """
        Remove a route.

        @param destination: Destination of the route that should be removed.
        @type destination: C{str}.
        @param xs: XML Stream to remove the route for.
        @type xs: L{EventDispatcher<utility.EventDispatcher>}.
        """
        xs.removeObserver("/*", self.route)
        if xs == self.routes[destination]:
            del self.routes[destination]

    def route(self, stanza):
        """
        Route a stanza.

        @param stanza: The stanza to be routed.
        @type stanza: L{domish.Element}.
        """
        destination = JID(stanza["to"])

        log.msg(f"Routing to {destination.full()}: {stanza.toXml()!r}")

        if destination.host in self.routes:
            self.routes[destination.host].send(stanza)
        else:
            self.routes[None].send(stanza)


class XMPPComponentServerFactory(xmlstream.XmlStreamServerFactory):
    """
    XMPP Component Server factory.

    This factory accepts XMPP external component connections and makes
    the router service route traffic for a component's bound domain
    to that component.

    @since: 8.2
    """

    logTraffic = False

    def __init__(self, router, secret="secret"):
        self.router = router
        self.secret = secret

        def authenticatorFactory():
            return ListenComponentAuthenticator(self.secret)

        xmlstream.XmlStreamServerFactory.__init__(self, authenticatorFactory)
        self.addBootstrap(xmlstream.STREAM_CONNECTED_EVENT, self.onConnectionMade)
        self.addBootstrap(xmlstream.STREAM_AUTHD_EVENT, self.onAuthenticated)

        self.serial = 0

    def onConnectionMade(self, xs):
        """
        Called when a component connection was made.

        This enables traffic debugging on incoming streams.
        """
        xs.serial = self.serial
        self.serial += 1

        def logDataIn(buf):
            log.msg("RECV (%d): %r" % (xs.serial, buf))

        def logDataOut(buf):
            log.msg("SEND (%d): %r" % (xs.serial, buf))

        if self.logTraffic:
            xs.rawDataInFn = logDataIn
            xs.rawDataOutFn = logDataOut

        xs.addObserver(xmlstream.STREAM_ERROR_EVENT, self.onError)

    def onAuthenticated(self, xs):
        """
        Called when a component has successfully authenticated.

        Add the component to the routing table and establish a handler
        for a closed connection.
        """
        destination = xs.thisEntity.host

        self.router.addRoute(destination, xs)
        xs.addObserver(
            xmlstream.STREAM_END_EVENT, self.onConnectionLost, 0, destination, xs
        )

    def onError(self, reason):
        log.err(reason, "Stream Error")

    def onConnectionLost(self, destination, xs, reason):
        self.router.removeRoute(destination, xs)
