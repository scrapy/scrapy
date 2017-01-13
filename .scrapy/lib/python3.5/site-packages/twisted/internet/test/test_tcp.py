# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{IReactorTCP} and the TCP parts of
L{IReactorSocket}.
"""

from __future__ import division, absolute_import

__metaclass__ = type

import errno
import socket

from functools import wraps

from zope.interface import implementer
from zope.interface.verify import verifyClass

from twisted.python.compat import long
from twisted.python.runtime import platform
from twisted.python.failure import Failure
from twisted.python import log

from twisted.trial.unittest import SkipTest, TestCase
from twisted.internet.error import (
    ConnectionLost, UserError, ConnectionRefusedError, ConnectionDone,
    ConnectionAborted, DNSLookupError, NoProtocol)
from twisted.internet.test.connectionmixins import (
    LogObserverMixin, ConnectionTestsMixin, StreamClientTestsMixin,
    findFreePort, ConnectableProtocol, EndpointCreator,
    runProtocolsWithReactor, Stop, BrokenContextFactory)
from twisted.internet.test.reactormixins import (
    ReactorBuilder, needsRunningReactor, stopOnError)
from twisted.internet.interfaces import (
    ILoggingContext, IConnector, IReactorFDSet, IReactorSocket, IReactorTCP,
    IResolverSimple, ITLSTransport)
from twisted.internet.address import IPv4Address, IPv6Address
from twisted.internet.defer import (
    Deferred, DeferredList, maybeDeferred, gatherResults, succeed, fail)
from twisted.internet.endpoints import TCP4ServerEndpoint, TCP4ClientEndpoint
from twisted.internet.protocol import ServerFactory, ClientFactory, Protocol
from twisted.internet.interfaces import (
    IPushProducer, IPullProducer, IHalfCloseableProtocol)
from twisted.internet.tcp import Connection, Server, _resolveIPv6
from twisted.internet.test.test_core import ObjectModelIntegrationMixin
from twisted.test.test_tcp import MyClientFactory, MyServerFactory
from twisted.test.test_tcp import ClosingFactory, ClientStartStopFactory

try:
    from OpenSSL import SSL
except ImportError:
    useSSL = False
else:
    from twisted.internet.ssl import ClientContextFactory
    useSSL = True

try:
    socket.socket(socket.AF_INET6, socket.SOCK_STREAM).close()
except socket.error as e:
    ipv6Skip = str(e)
else:
    ipv6Skip = None



if platform.isWindows():
    from twisted.internet.test import _win32ifaces
    getLinkLocalIPv6Addresses = _win32ifaces.win32GetLinkLocalIPv6Addresses
else:
    try:
        from twisted.internet.test import _posixifaces
    except ImportError:
        getLinkLocalIPv6Addresses = lambda: []
    else:
        getLinkLocalIPv6Addresses = _posixifaces.posixGetLinkLocalIPv6Addresses



def getLinkLocalIPv6Address():
    """
    Find and return a configured link local IPv6 address including a scope
    identifier using the % separation syntax.  If the system has no link local
    IPv6 addresses, raise L{SkipTest} instead.

    @raise SkipTest: if no link local address can be found or if the
        C{netifaces} module is not available.

    @return: a C{str} giving the address
    """
    addresses = getLinkLocalIPv6Addresses()
    if addresses:
        return addresses[0]
    raise SkipTest("Link local IPv6 address unavailable")



def connect(client, destination):
    """
    Connect a socket to the given destination.

    @param client: A C{socket.socket}.

    @param destination: A tuple of (host, port). The host is a C{str}, the
        port a C{int}. If the C{host} is an IPv6 IP, the address is resolved
        using C{getaddrinfo} and the first version found is used.
    """
    (host, port) = destination
    if '%' in host or ':' in host:
        address = socket.getaddrinfo(host, port)[0][4]
    else:
        address = (host, port)
    client.connect(address)



class FakeSocket(object):
    """
    A fake for L{socket.socket} objects.

    @ivar data: A C{str} giving the data which will be returned from
        L{FakeSocket.recv}.

    @ivar sendBuffer: A C{list} of the objects passed to L{FakeSocket.send}.
    """
    def __init__(self, data):
        self.data = data
        self.sendBuffer = []

    def setblocking(self, blocking):
        self.blocking = blocking

    def recv(self, size):
        return self.data

    def send(self, bytes):
        """
        I{Send} all of C{bytes} by accumulating it into C{self.sendBuffer}.

        @return: The length of C{bytes}, indicating all the data has been
            accepted.
        """
        self.sendBuffer.append(bytes)
        return len(bytes)


    def shutdown(self, how):
        """
        Shutdown is not implemented.  The method is provided since real sockets
        have it and some code expects it.  No behavior of L{FakeSocket} is
        affected by a call to it.
        """


    def close(self):
        """
        Close is not implemented.  The method is provided since real sockets
        have it and some code expects it.  No behavior of L{FakeSocket} is
        affected by a call to it.
        """


    def setsockopt(self, *args):
        """
        Setsockopt is not implemented.  The method is provided since
        real sockets have it and some code expects it.  No behavior of
        L{FakeSocket} is affected by a call to it.
        """


    def fileno(self):
        """
        Return a fake file descriptor.  If actually used, this will have no
        connection to this L{FakeSocket} and will probably cause surprising
        results.
        """
        return 1



class FakeSocketTests(TestCase):
    """
    Test that the FakeSocket can be used by the doRead method of L{Connection}
    """

    def test_blocking(self):
        skt = FakeSocket(b"someData")
        skt.setblocking(0)
        self.assertEqual(skt.blocking, 0)


    def test_recv(self):
        skt = FakeSocket(b"someData")
        self.assertEqual(skt.recv(10), b"someData")


    def test_send(self):
        """
        L{FakeSocket.send} accepts the entire string passed to it, adds it to
        its send buffer, and returns its length.
        """
        skt = FakeSocket(b"")
        count = skt.send(b"foo")
        self.assertEqual(count, 3)
        self.assertEqual(skt.sendBuffer, [b"foo"])



class FakeProtocol(Protocol):
    """
    An L{IProtocol} that returns a value from its dataReceived method.
    """
    def dataReceived(self, data):
        """
        Return something other than L{None} to trigger a deprecation warning for
        that behavior.
        """
        return ()



@implementer(IReactorFDSet)
class _FakeFDSetReactor(object):
    """
    An in-memory implementation of L{IReactorFDSet}, which records the current
    sets of active L{IReadDescriptor} and L{IWriteDescriptor}s.

    @ivar _readers: The set of L{IReadDescriptor}s active on this
        L{_FakeFDSetReactor}
    @type _readers: L{set}

    @ivar _writers: The set of L{IWriteDescriptor}s active on this
        L{_FakeFDSetReactor}
    @ivar _writers: L{set}
    """

    def __init__(self):
        self._readers = set()
        self._writers = set()


    def addReader(self, reader):
        self._readers.add(reader)


    def removeReader(self, reader):
        if reader in self._readers:
            self._readers.remove(reader)


    def addWriter(self, writer):
        self._writers.add(writer)


    def removeWriter(self, writer):
        if writer in self._writers:
            self._writers.remove(writer)


    def removeAll(self):
        result = self.getReaders() + self.getWriters()
        self.__init__()
        return result


    def getReaders(self):
        return list(self._readers)


    def getWriters(self):
        return list(self._writers)

verifyClass(IReactorFDSet, _FakeFDSetReactor)



class TCPServerTests(TestCase):
    """
    Whitebox tests for L{twisted.internet.tcp.Server}.
    """
    def setUp(self):
        self.reactor = _FakeFDSetReactor()
        class FakePort(object):
            _realPortNumber = 3
        self.skt = FakeSocket(b"")
        self.protocol = Protocol()
        self.server = Server(
            self.skt, self.protocol, ("", 0), FakePort(), None, self.reactor)


    def test_writeAfterDisconnect(self):
        """
        L{Server.write} discards bytes passed to it if called after it has lost
        its connection.
        """
        self.server.connectionLost(
            Failure(Exception("Simulated lost connection")))
        self.server.write(b"hello world")
        self.assertEqual(self.skt.sendBuffer, [])


    def test_writeAfterDisconnectAfterTLS(self):
        """
        L{Server.write} discards bytes passed to it if called after it has lost
        its connection when the connection had started TLS.
        """
        self.server.TLS = True
        self.test_writeAfterDisconnect()


    def test_writeSequenceAfterDisconnect(self):
        """
        L{Server.writeSequence} discards bytes passed to it if called after it
        has lost its connection.
        """
        self.server.connectionLost(
            Failure(Exception("Simulated lost connection")))
        self.server.writeSequence([b"hello world"])
        self.assertEqual(self.skt.sendBuffer, [])


    def test_writeSequenceAfterDisconnectAfterTLS(self):
        """
        L{Server.writeSequence} discards bytes passed to it if called after it
        has lost its connection when the connection had started TLS.
        """
        self.server.TLS = True
        self.test_writeSequenceAfterDisconnect()



class TCPConnectionTests(TestCase):
    """
    Whitebox tests for L{twisted.internet.tcp.Connection}.
    """
    def test_doReadWarningIsRaised(self):
        """
        When an L{IProtocol} implementation that returns a value from its
        C{dataReceived} method, a deprecated warning is emitted.
        """
        skt = FakeSocket(b"someData")
        protocol = FakeProtocol()
        conn = Connection(skt, protocol)
        conn.doRead()
        warnings = self.flushWarnings([FakeProtocol.dataReceived])
        self.assertEqual(warnings[0]['category'], DeprecationWarning)
        self.assertEqual(
            warnings[0]["message"],
            "Returning a value other than None from "
            "twisted.internet.test.test_tcp.FakeProtocol.dataReceived "
            "is deprecated since Twisted 11.0.0.")
        self.assertEqual(len(warnings), 1)


    def test_noTLSBeforeStartTLS(self):
        """
        The C{TLS} attribute of a L{Connection} instance is C{False} before
        L{Connection.startTLS} is called.
        """
        skt = FakeSocket(b"")
        protocol = FakeProtocol()
        conn = Connection(skt, protocol)
        self.assertFalse(conn.TLS)


    def test_tlsAfterStartTLS(self):
        """
        The C{TLS} attribute of a L{Connection} instance is C{True} after
        L{Connection.startTLS} is called.
        """
        skt = FakeSocket(b"")
        protocol = FakeProtocol()
        conn = Connection(skt, protocol, reactor=_FakeFDSetReactor())
        conn._tlsClientDefault = True
        conn.startTLS(ClientContextFactory(), True)
        self.assertTrue(conn.TLS)
    if not useSSL:
        test_tlsAfterStartTLS.skip = "No SSL support available"



class TCPCreator(EndpointCreator):
    """
    Create IPv4 TCP endpoints for L{runProtocolsWithReactor}-based tests.
    """

    interface = "127.0.0.1"

    def server(self, reactor):
        """
        Create a server-side TCP endpoint.
        """
        return TCP4ServerEndpoint(reactor, 0, interface=self.interface)


    def client(self, reactor, serverAddress):
        """
        Create a client end point that will connect to the given address.

        @type serverAddress: L{IPv4Address}
        """
        return TCP4ClientEndpoint(reactor, self.interface, serverAddress.port)



class TCP6Creator(TCPCreator):
    """
    Create IPv6 TCP endpoints for
    C{ReactorBuilder.runProtocolsWithReactor}-based tests.

    The endpoint types in question here are still the TCP4 variety, since
    these simply pass through IPv6 address literals to the reactor, and we are
    only testing address literals, not name resolution (as name resolution has
    not yet been implemented).  See http://twistedmatrix.com/trac/ticket/4470
    for more specific information about new endpoint classes.  The naming is
    slightly misleading, but presumably if you're passing an IPv6 literal, you
    know what you're asking for.
    """
    def __init__(self):
        self.interface = getLinkLocalIPv6Address()



@implementer(IResolverSimple)
class FakeResolver(object):
    """
    A resolver implementation based on a C{dict} mapping names to addresses.
    """

    def __init__(self, names):
        self.names = names


    def getHostByName(self, name, timeout):
        """
        Return the address mapped to C{name} if it exists, or raise a
        C{DNSLookupError}.

        @param name: The name to resolve.

        @param timeout: The lookup timeout, ignore here.
        """
        try:
            return succeed(self.names[name])
        except KeyError:
            return fail(DNSLookupError("FakeResolver couldn't find " + name))



class TCPClientTestsBase(ReactorBuilder, ConnectionTestsMixin,
                         StreamClientTestsMixin):
    """
    Base class for builders defining tests related to
    L{IReactorTCP.connectTCP}.  Classes which uses this in must provide all of
    the documented instance variables in order to specify how the test works.
    These are documented as instance variables rather than declared as methods
    due to some peculiar inheritance ordering concerns, but they are
    effectively abstract methods.

    @ivar endpoints: A client/server endpoint creator appropriate to the
        address family being tested.
    @type endpoints: L{twisted.internet.test.connectionmixins.EndpointCreator}

    @ivar interface: An IP address literal to locally bind a socket to as well
        as to connect to.  This can be any valid interface for the local host.
    @type interface: C{str}

    @ivar port: An unused local listening port to listen on and connect to.
        This will be used in conjunction with the C{interface}.  (Depending on
        what they're testing, some tests will locate their own port with
        L{findFreePort} instead.)
    @type port: C{int}

    @ivar family: an address family constant, such as L{socket.AF_INET},
        L{socket.AF_INET6}, or L{socket.AF_UNIX}, which indicates the address
        family of the transport type under test.
    @type family: C{int}

    @ivar addressClass: the L{twisted.internet.interfaces.IAddress} implementor
        associated with the transport type under test.  Must also be a
        3-argument callable which produces an instance of same.
    @type addressClass: C{type}

    @ivar fakeDomainName: A fake domain name to use, to simulate hostname
        resolution and to distinguish between hostnames and IP addresses where
        necessary.
    @type fakeDomainName: C{str}
    """
    requiredInterfaces = (IReactorTCP,)

    _port = None

    @property
    def port(self):
        """
        Return the port number to connect to, using C{self._port} set up by
        C{listen} if available.

        @return: The port number to connect to.
        @rtype: C{int}
        """
        if self._port is not None:
            return self._port.getHost().port
        return findFreePort(self.interface, self.family)[1]


    @property
    def interface(self):
        """
        Return the interface attribute from the endpoints object.
        """
        return self.endpoints.interface


    def listen(self, reactor, factory):
        """
        Start a TCP server with the given C{factory}.

        @param reactor: The reactor to create the TCP port in.

        @param factory: The server factory.

        @return: A TCP port instance.
        """
        self._port = reactor.listenTCP(0, factory, interface=self.interface)
        return self._port


    def connect(self, reactor, factory):
        """
        Start a TCP client with the given C{factory}.

        @param reactor: The reactor to create the connection in.

        @param factory: The client factory.

        @return: A TCP connector instance.
        """
        return reactor.connectTCP(self.interface, self.port, factory)


    def test_buildProtocolReturnsNone(self):
        """
        When the factory's C{buildProtocol} returns L{None} the connection is
        gracefully closed.
        """
        connectionLost = Deferred()
        reactor = self.buildReactor()
        serverFactory = MyServerFactory()
        serverFactory.protocolConnectionLost = connectionLost

        # Make sure the test ends quickly.
        stopOnError(self, reactor)

        class NoneFactory(ServerFactory):
            def buildProtocol(self, address):
                return None

        listening = self.endpoints.server(reactor).listen(serverFactory)

        def listened(port):
            clientFactory = NoneFactory()
            endpoint = self.endpoints.client(reactor, port.getHost())
            return endpoint.connect(clientFactory)
        connecting = listening.addCallback(listened)

        def connectSucceeded(protocol):
            self.fail(
                "Stream client endpoint connect succeeded with %r, "
                "should have failed with NoProtocol." % (protocol,))
        def connectFailed(reason):
            reason.trap(NoProtocol)
        connecting.addCallbacks(connectSucceeded, connectFailed)

        def connected(ignored):
            # Now that the connection attempt has failed continue waiting for
            # the server-side connection to be lost.  This is the behavior this
            # test is primarily concerned with.
            return connectionLost
        disconnecting = connecting.addCallback(connected)

        # Make sure any errors that happen in that process get logged quickly.
        disconnecting.addErrback(log.err)

        def disconnected(ignored):
            # The Deferred has to succeed at this point (because log.err always
            # returns None).  If an error got logged it will fail the test.
            # Stop the reactor now so the test can complete one way or the
            # other now.
            reactor.stop()
        disconnecting.addCallback(disconnected)

        self.runReactor(reactor)


    def test_addresses(self):
        """
        A client's transport's C{getHost} and C{getPeer} return L{IPv4Address}
        instances which have the dotted-quad string form of the resolved
        address of the local and remote endpoints of the connection
        respectively as their C{host} attribute, not the hostname originally
        passed in to
        L{connectTCP<twisted.internet.interfaces.IReactorTCP.connectTCP>}, if a
        hostname was used.
        """
        host, port = findFreePort(self.interface, self.family)[:2]
        reactor = self.buildReactor()
        fakeDomain = self.fakeDomainName
        reactor.installResolver(FakeResolver({fakeDomain: self.interface}))

        server = reactor.listenTCP(
            0, ServerFactory.forProtocol(Protocol), interface=host)
        serverAddress = server.getHost()

        transportData = {'host': None, 'peer': None, 'instance': None}

        class CheckAddress(Protocol):
            def makeConnection(self, transport):
                transportData['host'] = transport.getHost()
                transportData['peer'] = transport.getPeer()
                transportData['instance'] = transport
                reactor.stop()

        clientFactory = Stop(reactor)
        clientFactory.protocol = CheckAddress

        def connectMe():
            reactor.connectTCP(
                fakeDomain, server.getHost().port, clientFactory,
                bindAddress=(self.interface, port))
        needsRunningReactor(reactor, connectMe)

        self.runReactor(reactor)

        if clientFactory.failReason:
            self.fail(clientFactory.failReason.getTraceback())

        transportRepr = "<%s to %s at %x>" % (
            transportData['instance'].__class__,
            transportData['instance'].addr,
            id(transportData['instance']))

        self.assertEqual(
            transportData['host'],
            self.addressClass('TCP', self.interface, port))
        self.assertEqual(
            transportData['peer'],
            self.addressClass('TCP', self.interface, serverAddress.port))
        self.assertEqual(
            repr(transportData['instance']), transportRepr)


    def test_badContext(self):
        """
        If the context factory passed to L{ITCPTransport.startTLS} raises an
        exception from its C{getContext} method, that exception is raised by
        L{ITCPTransport.startTLS}.
        """
        reactor = self.buildReactor()

        brokenFactory = BrokenContextFactory()
        results = []

        serverFactory = ServerFactory.forProtocol(Protocol)
        port = reactor.listenTCP(0, serverFactory, interface=self.interface)
        endpoint = self.endpoints.client(reactor, port.getHost())

        clientFactory = ClientFactory()
        clientFactory.protocol = Protocol
        connectDeferred = endpoint.connect(clientFactory)

        def connected(protocol):
            if not ITLSTransport.providedBy(protocol.transport):
                results.append("skip")
            else:
                results.append(self.assertRaises(ValueError,
                                                 protocol.transport.startTLS,
                                                 brokenFactory))

        def connectFailed(failure):
            results.append(failure)

        def whenRun():
            connectDeferred.addCallback(connected)
            connectDeferred.addErrback(connectFailed)
            connectDeferred.addBoth(lambda ign: reactor.stop())
        needsRunningReactor(reactor, whenRun)

        self.runReactor(reactor)

        self.assertEqual(len(results), 1,
                         "more than one callback result: %s" % (results,))

        if isinstance(results[0], Failure):
            # self.fail(Failure)
            results[0].raiseException()
        if results[0] == "skip":
            raise SkipTest("Reactor does not support ITLSTransport")
        self.assertEqual(BrokenContextFactory.message, str(results[0]))



class TCP4ClientTestsBuilder(TCPClientTestsBase):
    """
    Builder configured with IPv4 parameters for tests related to
    L{IReactorTCP.connectTCP}.
    """
    fakeDomainName = 'some-fake.domain.example.com'
    family = socket.AF_INET
    addressClass = IPv4Address

    endpoints = TCPCreator()



class TCP6ClientTestsBuilder(TCPClientTestsBase):
    """
    Builder configured with IPv6 parameters for tests related to
    L{IReactorTCP.connectTCP}.
    """
    if ipv6Skip:
        skip = ipv6Skip

    family = socket.AF_INET6
    addressClass = IPv6Address

    def setUp(self):
        # Only create this object here, so that it won't be created if tests
        # are being skipped:
        self.endpoints = TCP6Creator()
        # This is used by test_addresses to test the distinction between the
        # resolved name and the name on the socket itself.  All the same
        # invariants should hold, but giving back an IPv6 address from a
        # resolver is not something the reactor can handle, so instead, we make
        # it so that the connect call for the IPv6 address test simply uses an
        # address literal.
        self.fakeDomainName = self.endpoints.interface



class TCPConnectorTestsBuilder(ReactorBuilder):
    """
    Tests for the L{IConnector} provider returned by L{IReactorTCP.connectTCP}.
    """
    requiredInterfaces = (IReactorTCP,)

    def test_connectorIdentity(self):
        """
        L{IReactorTCP.connectTCP} returns an object which provides
        L{IConnector}.  The destination of the connector is the address which
        was passed to C{connectTCP}.  The same connector object is passed to
        the factory's C{startedConnecting} method as to the factory's
        C{clientConnectionLost} method.
        """
        serverFactory = ClosingFactory()
        reactor = self.buildReactor()
        tcpPort = reactor.listenTCP(0, serverFactory, interface=self.interface)
        serverFactory.port = tcpPort
        portNumber = tcpPort.getHost().port

        seenConnectors = []
        seenFailures = []

        clientFactory = ClientStartStopFactory()
        clientFactory.clientConnectionLost = (
            lambda connector, reason: (seenConnectors.append(connector),
                                       seenFailures.append(reason)))
        clientFactory.startedConnecting = seenConnectors.append

        connector = reactor.connectTCP(self.interface, portNumber,
                                       clientFactory)
        self.assertTrue(IConnector.providedBy(connector))
        dest = connector.getDestination()
        self.assertEqual(dest.type, "TCP")
        self.assertEqual(dest.host, self.interface)
        self.assertEqual(dest.port, portNumber)

        clientFactory.whenStopped.addBoth(lambda _: reactor.stop())

        self.runReactor(reactor)

        seenFailures[0].trap(ConnectionDone)
        self.assertEqual(seenConnectors, [connector, connector])


    def test_userFail(self):
        """
        Calling L{IConnector.stopConnecting} in C{Factory.startedConnecting}
        results in C{Factory.clientConnectionFailed} being called with
        L{error.UserError} as the reason.
        """
        serverFactory = MyServerFactory()
        reactor = self.buildReactor()
        tcpPort = reactor.listenTCP(0, serverFactory, interface=self.interface)
        portNumber = tcpPort.getHost().port

        fatalErrors = []

        def startedConnecting(connector):
            try:
                connector.stopConnecting()
            except Exception:
                fatalErrors.append(Failure())
                reactor.stop()

        clientFactory = ClientStartStopFactory()
        clientFactory.startedConnecting = startedConnecting

        clientFactory.whenStopped.addBoth(lambda _: reactor.stop())

        reactor.callWhenRunning(lambda: reactor.connectTCP(self.interface,
                                                           portNumber,
                                                           clientFactory))

        self.runReactor(reactor)

        if fatalErrors:
            self.fail(fatalErrors[0].getTraceback())
        clientFactory.reason.trap(UserError)
        self.assertEqual(clientFactory.failed, 1)


    def test_reconnect(self):
        """
        Calling L{IConnector.connect} in C{Factory.clientConnectionLost} causes
        a new connection attempt to be made.
        """
        serverFactory = ClosingFactory()
        reactor = self.buildReactor()
        tcpPort = reactor.listenTCP(0, serverFactory, interface=self.interface)
        serverFactory.port = tcpPort
        portNumber = tcpPort.getHost().port

        clientFactory = MyClientFactory()

        def clientConnectionLost(connector, reason):
            connector.connect()
        clientFactory.clientConnectionLost = clientConnectionLost
        reactor.connectTCP(self.interface, portNumber, clientFactory)

        protocolMadeAndClosed = []
        def reconnectFailed(ignored):
            p = clientFactory.protocol
            protocolMadeAndClosed.append((p.made, p.closed))
            reactor.stop()

        clientFactory.failDeferred.addCallback(reconnectFailed)

        self.runReactor(reactor)

        clientFactory.reason.trap(ConnectionRefusedError)
        self.assertEqual(protocolMadeAndClosed, [(1, 1)])



class TCP4ConnectorTestsBuilder(TCPConnectorTestsBuilder):
    interface = '127.0.0.1'
    family = socket.AF_INET
    addressClass = IPv4Address



class TCP6ConnectorTestsBuilder(TCPConnectorTestsBuilder):
    family = socket.AF_INET6
    addressClass = IPv6Address

    if ipv6Skip:
        skip = ipv6Skip

    def setUp(self):
        self.interface = getLinkLocalIPv6Address()



def createTestSocket(test, addressFamily, socketType):
    """
    Create a socket for the duration of the given test.

    @param test: the test to add cleanup to.

    @param addressFamily: an C{AF_*} constant

    @param socketType: a C{SOCK_*} constant.

    @return: a socket object.
    """
    skt = socket.socket(addressFamily, socketType)
    test.addCleanup(skt.close)
    return skt



class StreamTransportTestsMixin(LogObserverMixin):
    """
    Mixin defining tests which apply to any port/connection based transport.
    """
    def test_startedListeningLogMessage(self):
        """
        When a port starts, a message including a description of the associated
        factory is logged.
        """
        loggedMessages = self.observe()
        reactor = self.buildReactor()

        @implementer(ILoggingContext)
        class SomeFactory(ServerFactory):
            def logPrefix(self):
                return "Crazy Factory"

        factory = SomeFactory()
        p = self.getListeningPort(reactor, factory)
        expectedMessage = self.getExpectedStartListeningLogMessage(
            p, "Crazy Factory")
        self.assertEqual((expectedMessage,), loggedMessages[0]['message'])


    def test_connectionLostLogMsg(self):
        """
        When a connection is lost, an informative message should be logged
        (see L{getExpectedConnectionLostLogMsg}): an address identifying
        the port and the fact that it was closed.
        """

        loggedMessages = []
        def logConnectionLostMsg(eventDict):
            loggedMessages.append(log.textFromEventDict(eventDict))

        reactor = self.buildReactor()
        p = self.getListeningPort(reactor, ServerFactory())
        expectedMessage = self.getExpectedConnectionLostLogMsg(p)
        log.addObserver(logConnectionLostMsg)

        def stopReactor(ignored):
            log.removeObserver(logConnectionLostMsg)
            reactor.stop()

        def doStopListening():
            log.addObserver(logConnectionLostMsg)
            maybeDeferred(p.stopListening).addCallback(stopReactor)

        reactor.callWhenRunning(doStopListening)
        reactor.run()

        self.assertIn(expectedMessage, loggedMessages)


    def test_allNewStyle(self):
        """
        The L{IListeningPort} object is an instance of a class with no
        classic classes in its hierarchy.
        """
        reactor = self.buildReactor()
        port = self.getListeningPort(reactor, ServerFactory())
        self.assertFullyNewStyle(port)


class ListenTCPMixin(object):
    """
    Mixin which uses L{IReactorTCP.listenTCP} to hand out listening TCP ports.
    """
    def getListeningPort(self, reactor, factory, port=0, interface=''):
        """
        Get a TCP port from a reactor.
        """
        return reactor.listenTCP(port, factory, interface=interface)



class SocketTCPMixin(object):
    """
    Mixin which uses L{IReactorSocket.adoptStreamPort} to hand out listening TCP
    ports.
    """
    def getListeningPort(self, reactor, factory, port=0, interface=''):
        """
        Get a TCP port from a reactor, wrapping an already-initialized file
        descriptor.
        """
        if IReactorSocket.providedBy(reactor):
            if ':' in interface:
                domain = socket.AF_INET6
                address = socket.getaddrinfo(interface, port)[0][4]
            else:
                domain = socket.AF_INET
                address = (interface, port)
            portSock = socket.socket(domain)
            portSock.bind(address)
            portSock.listen(3)
            portSock.setblocking(False)
            try:
                return reactor.adoptStreamPort(
                    portSock.fileno(), portSock.family, factory)
            finally:
                # The socket should still be open; fileno will raise if it is
                # not.
                portSock.fileno()
                # Now clean it up, because the rest of the test does not need
                # it.
                portSock.close()
        else:
            raise SkipTest("Reactor does not provide IReactorSocket")



class TCPPortTestsMixin(object):
    """
    Tests for L{IReactorTCP.listenTCP}
    """
    requiredInterfaces = (IReactorTCP,)

    def getExpectedStartListeningLogMessage(self, port, factory):
        """
        Get the message expected to be logged when a TCP port starts listening.
        """
        return "%s starting on %d" % (
            factory, port.getHost().port)


    def getExpectedConnectionLostLogMsg(self, port):
        """
        Get the expected connection lost message for a TCP port.
        """
        return "(TCP Port %s Closed)" % (port.getHost().port,)


    def test_portGetHostOnIPv4(self):
        """
        When no interface is passed to L{IReactorTCP.listenTCP}, the returned
        listening port listens on an IPv4 address.
        """
        reactor = self.buildReactor()
        port = self.getListeningPort(reactor, ServerFactory())
        address = port.getHost()
        self.assertIsInstance(address, IPv4Address)


    def test_portGetHostOnIPv6(self):
        """
        When listening on an IPv6 address, L{IListeningPort.getHost} returns
        an L{IPv6Address} with C{host} and C{port} attributes reflecting the
        address the port is bound to.
        """
        reactor = self.buildReactor()
        host, portNumber = findFreePort(
            family=socket.AF_INET6, interface='::1')[:2]
        port = self.getListeningPort(
            reactor, ServerFactory(), portNumber, host)
        address = port.getHost()
        self.assertIsInstance(address, IPv6Address)
        self.assertEqual('::1', address.host)
        self.assertEqual(portNumber, address.port)
    if ipv6Skip:
        test_portGetHostOnIPv6.skip = ipv6Skip


    def test_portGetHostOnIPv6ScopeID(self):
        """
        When a link-local IPv6 address including a scope identifier is passed as
        the C{interface} argument to L{IReactorTCP.listenTCP}, the resulting
        L{IListeningPort} reports its address as an L{IPv6Address} with a host
        value that includes the scope identifier.
        """
        linkLocal = getLinkLocalIPv6Address()
        reactor = self.buildReactor()
        port = self.getListeningPort(reactor, ServerFactory(), 0, linkLocal)
        address = port.getHost()
        self.assertIsInstance(address, IPv6Address)
        self.assertEqual(linkLocal, address.host)
    if ipv6Skip:
        test_portGetHostOnIPv6ScopeID.skip = ipv6Skip


    def _buildProtocolAddressTest(self, client, interface):
        """
        Connect C{client} to a server listening on C{interface} started with
        L{IReactorTCP.listenTCP} and return the address passed to the factory's
        C{buildProtocol} method.

        @param client: A C{SOCK_STREAM} L{socket.socket} created with an address
            family such that it will be able to connect to a server listening on
            C{interface}.

        @param interface: A C{str} giving an address for a server to listen on.
            This should almost certainly be the loopback address for some
            address family supported by L{IReactorTCP.listenTCP}.

        @return: Whatever object, probably an L{IAddress} provider, is passed to
            a server factory's C{buildProtocol} method when C{client}
            establishes a connection.
        """
        class ObserveAddress(ServerFactory):
            def buildProtocol(self, address):
                reactor.stop()
                self.observedAddress = address
                return Protocol()

        factory = ObserveAddress()
        reactor = self.buildReactor()
        port = self.getListeningPort(reactor, factory, 0, interface)
        client.setblocking(False)
        try:
            connect(client, (port.getHost().host, port.getHost().port))
        except socket.error as e:
            self.assertIn(e.errno, (errno.EINPROGRESS, errno.EWOULDBLOCK))

        self.runReactor(reactor)

        return factory.observedAddress


    def test_buildProtocolIPv4Address(self):
        """
        When a connection is accepted over IPv4, an L{IPv4Address} is passed
        to the factory's C{buildProtocol} method giving the peer's address.
        """
        interface = '127.0.0.1'
        client = createTestSocket(self, socket.AF_INET, socket.SOCK_STREAM)
        observedAddress = self._buildProtocolAddressTest(client, interface)
        self.assertEqual(
            IPv4Address('TCP', *client.getsockname()), observedAddress)


    def test_buildProtocolIPv6Address(self):
        """
        When a connection is accepted to an IPv6 address, an L{IPv6Address} is
        passed to the factory's C{buildProtocol} method giving the peer's
        address.
        """
        interface = '::1'
        client = createTestSocket(self, socket.AF_INET6, socket.SOCK_STREAM)
        observedAddress = self._buildProtocolAddressTest(client, interface)
        self.assertEqual(
            IPv6Address('TCP', *client.getsockname()[:2]), observedAddress)
    if ipv6Skip:
        test_buildProtocolIPv6Address.skip = ipv6Skip


    def test_buildProtocolIPv6AddressScopeID(self):
        """
        When a connection is accepted to a link-local IPv6 address, an
        L{IPv6Address} is passed to the factory's C{buildProtocol} method
        giving the peer's address, including a scope identifier.
        """
        interface = getLinkLocalIPv6Address()
        client = createTestSocket(self, socket.AF_INET6, socket.SOCK_STREAM)
        observedAddress = self._buildProtocolAddressTest(client, interface)
        self.assertEqual(
            IPv6Address('TCP', *client.getsockname()[:2]), observedAddress)
    if ipv6Skip:
        test_buildProtocolIPv6AddressScopeID.skip = ipv6Skip


    def _serverGetConnectionAddressTest(self, client, interface, which):
        """
        Connect C{client} to a server listening on C{interface} started with
        L{IReactorTCP.listenTCP} and return the address returned by one of the
        server transport's address lookup methods, C{getHost} or C{getPeer}.

        @param client: A C{SOCK_STREAM} L{socket.socket} created with an address
            family such that it will be able to connect to a server listening on
            C{interface}.

        @param interface: A C{str} giving an address for a server to listen on.
            This should almost certainly be the loopback address for some
            address family supported by L{IReactorTCP.listenTCP}.

        @param which: A C{str} equal to either C{"getHost"} or C{"getPeer"}
            determining which address will be returned.

        @return: Whatever object, probably an L{IAddress} provider, is returned
            from the method indicated by C{which}.
        """
        class ObserveAddress(Protocol):
            def makeConnection(self, transport):
                reactor.stop()
                self.factory.address = getattr(transport, which)()

        reactor = self.buildReactor()
        factory = ServerFactory()
        factory.protocol = ObserveAddress
        port = self.getListeningPort(reactor, factory, 0, interface)
        client.setblocking(False)
        try:
            connect(client, (port.getHost().host, port.getHost().port))
        except socket.error as e:
            self.assertIn(e.errno, (errno.EINPROGRESS, errno.EWOULDBLOCK))
        self.runReactor(reactor)
        return factory.address


    def test_serverGetHostOnIPv4(self):
        """
        When a connection is accepted over IPv4, the server
        L{ITransport.getHost} method returns an L{IPv4Address} giving the
        address on which the server accepted the connection.
        """
        interface = '127.0.0.1'
        client = createTestSocket(self, socket.AF_INET, socket.SOCK_STREAM)
        hostAddress = self._serverGetConnectionAddressTest(
            client, interface, 'getHost')
        self.assertEqual(
            IPv4Address('TCP', *client.getpeername()), hostAddress)


    def test_serverGetHostOnIPv6(self):
        """
        When a connection is accepted over IPv6, the server
        L{ITransport.getHost} method returns an L{IPv6Address} giving the
        address on which the server accepted the connection.
        """
        interface = '::1'
        client = createTestSocket(self, socket.AF_INET6, socket.SOCK_STREAM)
        hostAddress = self._serverGetConnectionAddressTest(
            client, interface, 'getHost')
        self.assertEqual(
            IPv6Address('TCP', *client.getpeername()[:2]), hostAddress)
    if ipv6Skip:
        test_serverGetHostOnIPv6.skip = ipv6Skip


    def test_serverGetHostOnIPv6ScopeID(self):
        """
        When a connection is accepted over IPv6, the server
        L{ITransport.getHost} method returns an L{IPv6Address} giving the
        address on which the server accepted the connection, including the scope
        identifier.
        """
        interface = getLinkLocalIPv6Address()
        client = createTestSocket(self, socket.AF_INET6, socket.SOCK_STREAM)
        hostAddress = self._serverGetConnectionAddressTest(
            client, interface, 'getHost')
        self.assertEqual(
            IPv6Address('TCP', *client.getpeername()[:2]), hostAddress)
    if ipv6Skip:
        test_serverGetHostOnIPv6ScopeID.skip = ipv6Skip


    def test_serverGetPeerOnIPv4(self):
        """
        When a connection is accepted over IPv4, the server
        L{ITransport.getPeer} method returns an L{IPv4Address} giving the
        address of the remote end of the connection.
        """
        interface = '127.0.0.1'
        client = createTestSocket(self, socket.AF_INET, socket.SOCK_STREAM)
        peerAddress = self._serverGetConnectionAddressTest(
            client, interface, 'getPeer')
        self.assertEqual(
            IPv4Address('TCP', *client.getsockname()), peerAddress)


    def test_serverGetPeerOnIPv6(self):
        """
        When a connection is accepted over IPv6, the server
        L{ITransport.getPeer} method returns an L{IPv6Address} giving the
        address on the remote end of the connection.
        """
        interface = '::1'
        client = createTestSocket(self, socket.AF_INET6, socket.SOCK_STREAM)
        peerAddress = self._serverGetConnectionAddressTest(
            client, interface, 'getPeer')
        self.assertEqual(
            IPv6Address('TCP', *client.getsockname()[:2]), peerAddress)
    if ipv6Skip:
        test_serverGetPeerOnIPv6.skip = ipv6Skip


    def test_serverGetPeerOnIPv6ScopeID(self):
        """
        When a connection is accepted over IPv6, the server
        L{ITransport.getPeer} method returns an L{IPv6Address} giving the
        address on the remote end of the connection, including the scope
        identifier.
        """
        interface = getLinkLocalIPv6Address()
        client = createTestSocket(self, socket.AF_INET6, socket.SOCK_STREAM)
        peerAddress = self._serverGetConnectionAddressTest(
            client, interface, 'getPeer')
        self.assertEqual(
            IPv6Address('TCP', *client.getsockname()[:2]), peerAddress)
    if ipv6Skip:
        test_serverGetPeerOnIPv6ScopeID.skip = ipv6Skip



class TCPPortTestsBuilder(ReactorBuilder, ListenTCPMixin, TCPPortTestsMixin,
                          ObjectModelIntegrationMixin,
                          StreamTransportTestsMixin):
    pass



class TCPFDPortTestsBuilder(ReactorBuilder, SocketTCPMixin, TCPPortTestsMixin,
                            ObjectModelIntegrationMixin,
                            StreamTransportTestsMixin):
    pass



class StopStartReadingProtocol(Protocol):
    """
    Protocol that pauses and resumes the transport a few times
    """

    def connectionMade(self):
        self.data = b''
        self.pauseResumeProducing(3)


    def pauseResumeProducing(self, counter):
        """
        Toggle transport read state, then count down.
        """
        self.transport.pauseProducing()
        self.transport.resumeProducing()
        if counter:
            self.factory.reactor.callLater(0,
                    self.pauseResumeProducing, counter - 1)
        else:
            self.factory.reactor.callLater(0,
                    self.factory.ready.callback, self)


    def dataReceived(self, data):
        log.msg('got data', len(data))
        self.data += data
        if len(self.data) == 4*4096:
            self.factory.stop.callback(self.data)



def oneTransportTest(testMethod):
    """
    Decorate a L{ReactorBuilder} test function which tests one reactor and one
    connected transport.  Run that test method in the context of
    C{connectionMade}, and immediately drop the connection (and end the test)
    when that completes.

    @param testMethod: A unit test method on a L{ReactorBuilder} test suite;
        taking two additional parameters; a C{reactor} as built by the
        L{ReactorBuilder}, and an L{ITCPTransport} provider.
    @type testMethod: 3-argument C{function}

    @return: a no-argument test method.
    @rtype: 1-argument C{function}
    """
    @wraps(testMethod)
    def actualTestMethod(builder):
        other = ConnectableProtocol()
        class ServerProtocol(ConnectableProtocol):
            def connectionMade(self):
                try:
                    testMethod(builder, self.reactor, self.transport)
                finally:
                    if self.transport is not None:
                        self.transport.loseConnection()
                    if other.transport is not None:
                        other.transport.loseConnection()
        serverProtocol = ServerProtocol()
        runProtocolsWithReactor(builder, serverProtocol, other, TCPCreator())
    return actualTestMethod



def assertReading(testCase, reactor, transport):
    """
    Use the given test to assert that the given transport is actively reading
    in the given reactor.

    @note: Maintainers; for more information on why this is a function rather
        than a method on a test case, see U{this document on how we structure
        test tools
        <http://twistedmatrix.com/trac/wiki/Design/KeepTestToolsOutOfFixtures>}

    @param testCase: a test case to perform the assertion upon.
    @type testCase: L{TestCase}

    @param reactor: A reactor, possibly one providing L{IReactorFDSet}, or an
        IOCP reactor.

    @param transport: An L{ITCPTransport}
    """
    if IReactorFDSet.providedBy(reactor):
        testCase.assertIn(transport, reactor.getReaders())
    else:
        # IOCP.
        testCase.assertIn(transport, reactor.handles)
        testCase.assertTrue(transport.reading)



def assertNotReading(testCase, reactor, transport):
    """
    Use the given test to assert that the given transport is I{not} actively
    reading in the given reactor.

    @note: Maintainers; for more information on why this is a function rather
        than a method on a test case, see U{this document on how we structure
        test tools
        <http://twistedmatrix.com/trac/wiki/Design/KeepTestToolsOutOfFixtures>}

    @param testCase: a test case to perform the assertion upon.
    @type testCase: L{TestCase}

    @param reactor: A reactor, possibly one providing L{IReactorFDSet}, or an
        IOCP reactor.

    @param transport: An L{ITCPTransport}
    """
    if IReactorFDSet.providedBy(reactor):
        testCase.assertNotIn(transport, reactor.getReaders())
    else:
        # IOCP.
        testCase.assertFalse(transport.reading)



class TCPConnectionTestsBuilder(ReactorBuilder):
    """
    Builder defining tests relating to L{twisted.internet.tcp.Connection}.
    """
    requiredInterfaces = (IReactorTCP,)

    def test_stopStartReading(self):
        """
        This test verifies transport socket read state after multiple
        pause/resumeProducing calls.
        """
        sf = ServerFactory()
        reactor = sf.reactor = self.buildReactor()

        skippedReactors = ["Glib2Reactor", "Gtk2Reactor"]
        reactorClassName = reactor.__class__.__name__
        if reactorClassName in skippedReactors and platform.isWindows():
            raise SkipTest(
                "This test is broken on gtk/glib under Windows.")

        sf.protocol = StopStartReadingProtocol
        sf.ready = Deferred()
        sf.stop = Deferred()
        p = reactor.listenTCP(0, sf)
        port = p.getHost().port
        def proceed(protos, port):
            """
            Send several IOCPReactor's buffers' worth of data.
            """
            self.assertTrue(protos[0])
            self.assertTrue(protos[1])
            protos = protos[0][1], protos[1][1]
            protos[0].transport.write(b'x' * (2 * 4096) + b'y' * (2 * 4096))
            return (sf.stop.addCallback(cleanup, protos, port)
                           .addCallback(lambda ign: reactor.stop()))

        def cleanup(data, protos, port):
            """
            Make sure IOCPReactor didn't start several WSARecv operations
            that clobbered each other's results.
            """
            self.assertEqual(data, b'x'*(2*4096) + b'y'*(2*4096),
                                 'did not get the right data')
            return DeferredList([
                    maybeDeferred(protos[0].transport.loseConnection),
                    maybeDeferred(protos[1].transport.loseConnection),
                    maybeDeferred(port.stopListening)])

        cc = TCP4ClientEndpoint(reactor, '127.0.0.1', port)
        cf = ClientFactory()
        cf.protocol = Protocol
        d = DeferredList([cc.connect(cf), sf.ready]).addCallback(proceed, p)
        d.addErrback(log.err)
        self.runReactor(reactor)


    @oneTransportTest
    def test_resumeProducing(self, reactor, server):
        """
        When a L{Server} is connected, its C{resumeProducing} method adds it as
        a reader to the reactor.
        """
        server.pauseProducing()
        assertNotReading(self, reactor, server)
        server.resumeProducing()
        assertReading(self, reactor, server)


    @oneTransportTest
    def test_resumeProducingWhileDisconnecting(self, reactor, server):
        """
        When a L{Server} has already started disconnecting via
        C{loseConnection}, its C{resumeProducing} method does not add it as a
        reader to its reactor.
        """
        server.loseConnection()
        server.resumeProducing()
        assertNotReading(self, reactor, server)


    @oneTransportTest
    def test_resumeProducingWhileDisconnected(self, reactor, server):
        """
        When a L{Server} has already lost its connection, its
        C{resumeProducing} method does not add it as a reader to its reactor.
        """
        server.connectionLost(Failure(Exception("dummy")))
        assertNotReading(self, reactor, server)
        server.resumeProducing()
        assertNotReading(self, reactor, server)


    def test_connectionLostAfterPausedTransport(self):
        """
        Alice connects to Bob.  Alice writes some bytes and then shuts down the
        connection.  Bob receives the bytes from the connection and then pauses
        the transport object.  Shortly afterwards Bob resumes the transport
        object.  At that point, Bob is notified that the connection has been
        closed.

        This is no problem for most reactors.  The underlying event notification
        API will probably just remind them that the connection has been closed.
        It is a little tricky for win32eventreactor (MsgWaitForMultipleObjects).
        MsgWaitForMultipleObjects will only deliver the close notification once.
        The reactor needs to remember that notification until Bob resumes the
        transport.
        """
        class Pauser(ConnectableProtocol):
            def __init__(self):
                self.events = []

            def dataReceived(self, bytes):
                self.events.append("paused")
                self.transport.pauseProducing()
                self.reactor.callLater(0, self.resume)

            def resume(self):
                self.events.append("resumed")
                self.transport.resumeProducing()

            def connectionLost(self, reason):
                # This is the event you have been waiting for.
                self.events.append("lost")
                ConnectableProtocol.connectionLost(self, reason)

        class Client(ConnectableProtocol):
            def connectionMade(self):
                self.transport.write(b"some bytes for you")
                self.transport.loseConnection()

        pauser = Pauser()
        runProtocolsWithReactor(self, pauser, Client(), TCPCreator())
        self.assertEqual(pauser.events, ["paused", "resumed", "lost"])


    def test_doubleHalfClose(self):
        """
        If one side half-closes its connection, and then the other side of the
        connection calls C{loseWriteConnection}, and then C{loseConnection} in
        {writeConnectionLost}, the connection is closed correctly.

        This rather obscure case used to fail (see ticket #3037).
        """
        @implementer(IHalfCloseableProtocol)
        class ListenerProtocol(ConnectableProtocol):

            def readConnectionLost(self):
                self.transport.loseWriteConnection()

            def writeConnectionLost(self):
                self.transport.loseConnection()

        class Client(ConnectableProtocol):
            def connectionMade(self):
                self.transport.loseConnection()

        # If test fails, reactor won't stop and we'll hit timeout:
        runProtocolsWithReactor(
            self, ListenerProtocol(), Client(), TCPCreator())



class WriteSequenceTestsMixin(object):
    """
    Test for L{twisted.internet.abstract.FileDescriptor.writeSequence}.
    """
    requiredInterfaces = (IReactorTCP,)

    def setWriteBufferSize(self, transport, value):
        """
        Set the write buffer size for the given transport, mananing possible
        differences (ie, IOCP). Bug #4322 should remove the need of that hack.
        """
        if getattr(transport, "writeBufferSize", None) is not None:
            transport.writeBufferSize = value
        else:
            transport.bufferSize = value


    def test_writeSequeceWithoutWrite(self):
        """
        C{writeSequence} sends the data even if C{write} hasn't been called.
        """

        def connected(protocols):
            client, server, port = protocols

            def dataReceived(data):
                log.msg("data received: %r" % data)
                self.assertEqual(data, b"Some sequence splitted")
                client.transport.loseConnection()

            server.dataReceived = dataReceived

            client.transport.writeSequence([b"Some ", b"sequence ", b"splitted"])

        reactor = self.buildReactor()
        d = self.getConnectedClientAndServer(reactor, "127.0.0.1",
                                             socket.AF_INET)
        d.addCallback(connected)
        d.addErrback(log.err)
        self.runReactor(reactor)


    def test_writeSequenceWithUnicodeRaisesException(self):
        """
        C{writeSequence} with an element in the sequence of type unicode raises
        C{TypeError}.
        """

        def connected(protocols):
            client, server, port = protocols

            exc = self.assertRaises(
                TypeError,
                server.transport.writeSequence, [u"Unicode is not kosher"])

            self.assertEqual(str(exc), "Data must not be unicode")

            server.transport.loseConnection()

        reactor = self.buildReactor()
        d = self.getConnectedClientAndServer(reactor, "127.0.0.1",
                                             socket.AF_INET)
        d.addCallback(connected)
        d.addErrback(log.err)
        self.runReactor(reactor)


    def test_streamingProducer(self):
        """
        C{writeSequence} pauses its streaming producer if too much data is
        buffered, and then resumes it.
        """
        @implementer(IPushProducer)
        class SaveActionProducer(object):
            client = None
            server = None

            def __init__(self):
                self.actions = []

            def pauseProducing(self):
                self.actions.append("pause")

            def resumeProducing(self):
                self.actions.append("resume")
                # Unregister the producer so the connection can close
                self.client.transport.unregisterProducer()
                # This is why the code below waits for the server connection
                # first - so we have it to close here.  We close the server
                # side because win32evenreactor cannot reliably observe us
                # closing the client side (#5285).
                self.server.transport.loseConnection()

            def stopProducing(self):
                self.actions.append("stop")

        producer = SaveActionProducer()

        def connected(protocols):
            client, server = protocols[:2]
            producer.client = client
            producer.server = server
            # Register a streaming producer and verify that it gets paused
            # after it writes more than the local send buffer can hold.
            client.transport.registerProducer(producer, True)
            self.assertEqual(producer.actions, [])
            self.setWriteBufferSize(client.transport, 500)
            client.transport.writeSequence([b"x" * 50] * 20)
            self.assertEqual(producer.actions, ["pause"])

        reactor = self.buildReactor()
        d = self.getConnectedClientAndServer(reactor, "127.0.0.1",
                                             socket.AF_INET)
        d.addCallback(connected)
        d.addErrback(log.err)
        self.runReactor(reactor)
        # After the send buffer gets a chance to empty out a bit, the producer
        # should be resumed.
        self.assertEqual(producer.actions, ["pause", "resume"])


    def test_nonStreamingProducer(self):
        """
        C{writeSequence} pauses its producer if too much data is buffered only
        if this is a streaming producer.
        """
        test = self

        @implementer(IPullProducer)
        class SaveActionProducer(object):
            client = None

            def __init__(self):
                self.actions = []

            def resumeProducing(self):
                self.actions.append("resume")
                if self.actions.count("resume") == 2:
                    self.client.transport.stopConsuming()
                else:
                    test.setWriteBufferSize(self.client.transport, 500)
                    self.client.transport.writeSequence([b"x" * 50] * 20)

            def stopProducing(self):
                self.actions.append("stop")


        producer = SaveActionProducer()

        def connected(protocols):
            client = protocols[0]
            producer.client = client
            # Register a non-streaming producer and verify that it is resumed
            # immediately.
            client.transport.registerProducer(producer, False)
            self.assertEqual(producer.actions, ["resume"])

        reactor = self.buildReactor()
        d = self.getConnectedClientAndServer(reactor, "127.0.0.1",
                                             socket.AF_INET)
        d.addCallback(connected)
        d.addErrback(log.err)
        self.runReactor(reactor)
        # After the local send buffer empties out, the producer should be
        # resumed again.
        self.assertEqual(producer.actions, ["resume", "resume"])



class TCPTransportServerAddressTestMixin(object):
    """
    Test mixing for TCP server address building and log prefix.
    """

    def getConnectedClientAndServer(self, reactor, interface, addressFamily):
        """
        Helper method returnine a L{Deferred} firing with a tuple of a client
        protocol, a server protocol, and a running TCP port.
        """
        raise NotImplementedError()


    def _testServerAddress(self, interface, addressFamily, adressClass):
        """
        Helper method to test TCP server addresses on either IPv4 or IPv6.
        """

        def connected(protocols):
            client, server, port = protocols
            try:
                self.assertEqual(
                    "<AccumulatingProtocol #%s on %s>" %
                        (server.transport.sessionno, port.getHost().port),
                    str(server.transport))

                self.assertEqual(
                    "AccumulatingProtocol,%s,%s" %
                        (server.transport.sessionno, interface),
                    server.transport.logstr)

                [peerAddress] = server.factory.peerAddresses
                self.assertIsInstance(peerAddress, adressClass)
                self.assertEqual('TCP', peerAddress.type)
                self.assertEqual(interface, peerAddress.host)
            finally:
                # Be certain to drop the connection so the test completes.
                server.transport.loseConnection()

        reactor = self.buildReactor()
        d = self.getConnectedClientAndServer(reactor, interface, addressFamily)
        d.addCallback(connected)
        d.addErrback(log.err)
        self.runReactor(reactor)


    def test_serverAddressTCP4(self):
        """
        L{Server} instances have a string representation indicating on which
        port they're running, and the connected address is stored on the
        C{peerAddresses} attribute of the factory.
        """
        return self._testServerAddress("127.0.0.1", socket.AF_INET,
                                       IPv4Address)


    def test_serverAddressTCP6(self):
        """
        IPv6 L{Server} instances have a string representation indicating on
        which port they're running, and the connected address is stored on the
        C{peerAddresses} attribute of the factory.
        """
        return self._testServerAddress(getLinkLocalIPv6Address(),
                                       socket.AF_INET6, IPv6Address)

    if ipv6Skip:
        test_serverAddressTCP6.skip = ipv6Skip



class TCPTransportTestsBuilder(TCPTransportServerAddressTestMixin,
                               WriteSequenceTestsMixin, ReactorBuilder):
    """
    Test standard L{ITCPTransport}s built with C{listenTCP} and C{connectTCP}.
    """

    def getConnectedClientAndServer(self, reactor, interface, addressFamily):
        """
        Return a L{Deferred} firing with a L{MyClientFactory} and
        L{MyServerFactory} connected pair, and the listening C{Port}.
        """
        server = MyServerFactory()
        server.protocolConnectionMade = Deferred()
        server.protocolConnectionLost = Deferred()

        client = MyClientFactory()
        client.protocolConnectionMade = Deferred()
        client.protocolConnectionLost = Deferred()

        port = reactor.listenTCP(0, server, interface=interface)

        lostDeferred = gatherResults([client.protocolConnectionLost,
                                      server.protocolConnectionLost])
        def stop(result):
            reactor.stop()
            return result

        lostDeferred.addBoth(stop)

        startDeferred = gatherResults([client.protocolConnectionMade,
                                       server.protocolConnectionMade])

        deferred = Deferred()

        def start(protocols):
            client, server = protocols
            log.msg("client connected %s" % client)
            log.msg("server connected %s" % server)
            deferred.callback((client, server, port))

        startDeferred.addCallback(start)

        reactor.connectTCP(interface, port.getHost().port, client)

        return deferred



class AdoptStreamConnectionTestsBuilder(TCPTransportServerAddressTestMixin,
                                        WriteSequenceTestsMixin,
                                        ReactorBuilder):
    """
    Test server transports built using C{adoptStreamConnection}.
    """
    requiredInterfaces = (IReactorFDSet, IReactorSocket)

    def getConnectedClientAndServer(self, reactor, interface, addressFamily):
        """
        Return a L{Deferred} firing with a L{MyClientFactory} and
        L{MyServerFactory} connected pair, and the listening C{Port}. The
        particularity is that the server protocol has been obtained after doing
        a C{adoptStreamConnection} against the original server connection.
        """
        firstServer = MyServerFactory()
        firstServer.protocolConnectionMade = Deferred()

        server = MyServerFactory()
        server.protocolConnectionMade = Deferred()
        server.protocolConnectionLost = Deferred()

        client = MyClientFactory()
        client.protocolConnectionMade = Deferred()
        client.protocolConnectionLost = Deferred()

        port = reactor.listenTCP(0, firstServer, interface=interface)

        def firtServerConnected(proto):
            reactor.removeReader(proto.transport)
            reactor.removeWriter(proto.transport)
            reactor.adoptStreamConnection(
                proto.transport.fileno(), addressFamily, server)

        firstServer.protocolConnectionMade.addCallback(firtServerConnected)

        lostDeferred = gatherResults([client.protocolConnectionLost,
                                      server.protocolConnectionLost])
        def stop(result):
            if reactor.running:
                reactor.stop()
            return result

        lostDeferred.addBoth(stop)

        deferred = Deferred()
        deferred.addErrback(stop)

        startDeferred = gatherResults([client.protocolConnectionMade,
                                       server.protocolConnectionMade])
        def start(protocols):
            client, server = protocols
            log.msg("client connected %s" % client)
            log.msg("server connected %s" % server)
            deferred.callback((client, server, port))

        startDeferred.addCallback(start)

        reactor.connectTCP(interface, port.getHost().port, client)
        return deferred



globals().update(TCP4ClientTestsBuilder.makeTestCaseClasses())
globals().update(TCP6ClientTestsBuilder.makeTestCaseClasses())
globals().update(TCPPortTestsBuilder.makeTestCaseClasses())
globals().update(TCPFDPortTestsBuilder.makeTestCaseClasses())
globals().update(TCPConnectionTestsBuilder.makeTestCaseClasses())
globals().update(TCP4ConnectorTestsBuilder.makeTestCaseClasses())
globals().update(TCP6ConnectorTestsBuilder.makeTestCaseClasses())
globals().update(TCPTransportTestsBuilder.makeTestCaseClasses())
globals().update(AdoptStreamConnectionTestsBuilder.makeTestCaseClasses())



class ServerAbortsTwice(ConnectableProtocol):
    """
    Call abortConnection() twice.
    """

    def dataReceived(self, data):
        self.transport.abortConnection()
        self.transport.abortConnection()



class ServerAbortsThenLoses(ConnectableProtocol):
    """
    Call abortConnection() followed by loseConnection().
    """

    def dataReceived(self, data):
        self.transport.abortConnection()
        self.transport.loseConnection()



class AbortServerWritingProtocol(ConnectableProtocol):
    """
    Protocol that writes data upon connection.
    """

    def connectionMade(self):
        """
        Tell the client that the connection is set up and it's time to abort.
        """
        self.transport.write(b"ready")



class ReadAbortServerProtocol(AbortServerWritingProtocol):
    """
    Server that should never receive any data, except 'X's which are written
    by the other side of the connection before abortConnection, and so might
    possibly arrive.
    """

    def dataReceived(self, data):
        if data.replace(b'X', b''):
            raise Exception("Unexpectedly received data.")



class NoReadServer(ConnectableProtocol):
    """
    Stop reading immediately on connection.

    This simulates a lost connection that will cause the other side to time
    out, and therefore call abortConnection().
    """

    def connectionMade(self):
        self.transport.stopReading()



class EventualNoReadServer(ConnectableProtocol):
    """
    Like NoReadServer, except we Wait until some bytes have been delivered
    before stopping reading. This means TLS handshake has finished, where
    applicable.
    """

    gotData = False
    stoppedReading = False


    def dataReceived(self, data):
        if not self.gotData:
            self.gotData = True
            self.transport.registerProducer(self, False)
            self.transport.write(b"hello")


    def resumeProducing(self):
        if self.stoppedReading:
            return
        self.stoppedReading = True
        # We've written out the data:
        self.transport.stopReading()


    def pauseProducing(self):
        pass


    def stopProducing(self):
        pass



class BaseAbortingClient(ConnectableProtocol):
    """
    Base class for abort-testing clients.
    """
    inReactorMethod = False

    def connectionLost(self, reason):
        if self.inReactorMethod:
            raise RuntimeError("BUG: connectionLost was called re-entrantly!")
        ConnectableProtocol.connectionLost(self, reason)



class WritingButNotAbortingClient(BaseAbortingClient):
    """
    Write data, but don't abort.
    """

    def connectionMade(self):
        self.transport.write(b"hello")



class AbortingClient(BaseAbortingClient):
    """
    Call abortConnection() after writing some data.
    """

    def dataReceived(self, data):
        """
        Some data was received, so the connection is set up.
        """
        self.inReactorMethod = True
        self.writeAndAbort()
        self.inReactorMethod = False


    def writeAndAbort(self):
        # X is written before abortConnection, and so there is a chance it
        # might arrive. Y is written after, and so no Ys should ever be
        # delivered:
        self.transport.write(b"X" * 10000)
        self.transport.abortConnection()
        self.transport.write(b"Y" * 10000)



class AbortingTwiceClient(AbortingClient):
    """
    Call abortConnection() twice, after writing some data.
    """

    def writeAndAbort(self):
        AbortingClient.writeAndAbort(self)
        self.transport.abortConnection()



class AbortingThenLosingClient(AbortingClient):
    """
    Call abortConnection() and then loseConnection().
    """

    def writeAndAbort(self):
        AbortingClient.writeAndAbort(self)
        self.transport.loseConnection()



class ProducerAbortingClient(ConnectableProtocol):
    """
    Call abortConnection from doWrite, via resumeProducing.
    """

    inReactorMethod = True
    producerStopped = False

    def write(self):
        self.transport.write(b"lalala" * 127000)
        self.inRegisterProducer = True
        self.transport.registerProducer(self, False)
        self.inRegisterProducer = False


    def connectionMade(self):
        self.write()


    def resumeProducing(self):
        self.inReactorMethod = True
        if not self.inRegisterProducer:
            self.transport.abortConnection()
        self.inReactorMethod = False


    def stopProducing(self):
        self.producerStopped = True


    def connectionLost(self, reason):
        if not self.producerStopped:
            raise RuntimeError("BUG: stopProducing() was never called.")
        if self.inReactorMethod:
            raise RuntimeError("BUG: connectionLost called re-entrantly!")
        ConnectableProtocol.connectionLost(self, reason)



class StreamingProducerClient(ConnectableProtocol):
    """
    Call abortConnection() when the other side has stopped reading.

    In particular, we want to call abortConnection() only once our local
    socket hits a state where it is no longer writeable. This helps emulate
    the most common use case for abortConnection(), closing a connection after
    a timeout, with write buffers being full.

    Since it's very difficult to know when this actually happens, we just
    write a lot of data, and assume at that point no more writes will happen.
    """
    paused = False
    extraWrites = 0
    inReactorMethod = False

    def connectionMade(self):
        self.write()


    def write(self):
        """
        Write large amount to transport, then wait for a while for buffers to
        fill up.
        """
        self.transport.registerProducer(self, True)
        for i in range(100):
            self.transport.write(b"1234567890" * 32000)


    def resumeProducing(self):
        self.paused = False


    def stopProducing(self):
        pass


    def pauseProducing(self):
        """
        Called when local buffer fills up.

        The goal is to hit the point where the local file descriptor is not
        writeable (or the moral equivalent). The fact that pauseProducing has
        been called is not sufficient, since that can happen when Twisted's
        buffers fill up but OS hasn't gotten any writes yet. We want to be as
        close as possible to every buffer (including OS buffers) being full.

        So, we wait a bit more after this for Twisted to write out a few
        chunks, then abortConnection.
        """
        if self.paused:
            return
        self.paused = True
        # The amount we wait is arbitrary, we just want to make sure some
        # writes have happened and outgoing OS buffers filled up -- see
        # http://twistedmatrix.com/trac/ticket/5303 for details:
        self.reactor.callLater(0.01, self.doAbort)


    def doAbort(self):
        if not self.paused:
            log.err(RuntimeError("BUG: We should be paused a this point."))
        self.inReactorMethod = True
        self.transport.abortConnection()
        self.inReactorMethod = False


    def connectionLost(self, reason):
        # Tell server to start reading again so it knows to go away:
        self.otherProtocol.transport.startReading()
        ConnectableProtocol.connectionLost(self, reason)



class StreamingProducerClientLater(StreamingProducerClient):
    """
    Call abortConnection() from dataReceived, after bytes have been
    exchanged.
    """

    def connectionMade(self):
        self.transport.write(b"hello")
        self.gotData = False


    def dataReceived(self, data):
        if not self.gotData:
            self.gotData = True
            self.write()


class ProducerAbortingClientLater(ProducerAbortingClient):
    """
    Call abortConnection from doWrite, via resumeProducing.

    Try to do so after some bytes have already been exchanged, so we
    don't interrupt SSL handshake.
    """

    def connectionMade(self):
        # Override base class connectionMade().
        pass


    def dataReceived(self, data):
        self.write()



class DataReceivedRaisingClient(AbortingClient):
    """
    Call abortConnection(), and then throw exception, from dataReceived.
    """

    def dataReceived(self, data):
        self.transport.abortConnection()
        raise ZeroDivisionError("ONO")



class ResumeThrowsClient(ProducerAbortingClient):
    """
    Call abortConnection() and throw exception from resumeProducing().
    """

    def resumeProducing(self):
        if not self.inRegisterProducer:
            self.transport.abortConnection()
            raise ZeroDivisionError("ono!")


    def connectionLost(self, reason):
        # Base class assertion about stopProducing being called isn't valid;
        # if the we blew up in resumeProducing, consumers are justified in
        # giving up on the producer and not calling stopProducing.
        ConnectableProtocol.connectionLost(self, reason)



class AbortConnectionMixin(object):
    """
    Unit tests for L{ITransport.abortConnection}.
    """
    # Override in subclasses, should be an EndpointCreator instance:
    endpoints = None

    def runAbortTest(self, clientClass, serverClass,
                     clientConnectionLostReason=None):
        """
        A test runner utility function, which hooks up a matched pair of client
        and server protocols.

        We then run the reactor until both sides have disconnected, and then
        verify that the right exception resulted.
        """
        clientExpectedExceptions = (ConnectionAborted, ConnectionLost)
        serverExpectedExceptions = (ConnectionLost, ConnectionDone)
        # In TLS tests we may get SSL.Error instead of ConnectionLost,
        # since we're trashing the TLS protocol layer.
        if useSSL:
            clientExpectedExceptions = clientExpectedExceptions + (SSL.Error,)
            serverExpectedExceptions = serverExpectedExceptions + (SSL.Error,)

        client = clientClass()
        server = serverClass()
        client.otherProtocol = server
        server.otherProtocol = client
        reactor = runProtocolsWithReactor(self, server, client, self.endpoints)

        # Make sure everything was shutdown correctly:
        self.assertEqual(reactor.removeAll(), [])
        self.assertEqual(reactor.getDelayedCalls(), [])

        if clientConnectionLostReason is not None:
            self.assertIsInstance(
                client.disconnectReason.value,
                (clientConnectionLostReason,) + clientExpectedExceptions)
        else:
            self.assertIsInstance(client.disconnectReason.value,
                                  clientExpectedExceptions)
        self.assertIsInstance(server.disconnectReason.value, serverExpectedExceptions)


    def test_dataReceivedAbort(self):
        """
        abortConnection() is called in dataReceived. The protocol should be
        disconnected, but connectionLost should not be called re-entrantly.
        """
        return self.runAbortTest(AbortingClient, ReadAbortServerProtocol)


    def test_clientAbortsConnectionTwice(self):
        """
        abortConnection() is called twice by client.

        No exception should be thrown, and the connection will be closed.
        """
        return self.runAbortTest(AbortingTwiceClient, ReadAbortServerProtocol)


    def test_clientAbortsConnectionThenLosesConnection(self):
        """
        Client calls abortConnection(), followed by loseConnection().

        No exception should be thrown, and the connection will be closed.
        """
        return self.runAbortTest(AbortingThenLosingClient,
                                 ReadAbortServerProtocol)


    def test_serverAbortsConnectionTwice(self):
        """
        abortConnection() is called twice by server.

        No exception should be thrown, and the connection will be closed.
        """
        return self.runAbortTest(WritingButNotAbortingClient, ServerAbortsTwice,
                                 clientConnectionLostReason=ConnectionLost)


    def test_serverAbortsConnectionThenLosesConnection(self):
        """
        Server calls abortConnection(), followed by loseConnection().

        No exception should be thrown, and the connection will be closed.
        """
        return self.runAbortTest(WritingButNotAbortingClient,
                                 ServerAbortsThenLoses,
                                 clientConnectionLostReason=ConnectionLost)


    def test_resumeProducingAbort(self):
        """
        abortConnection() is called in resumeProducing, before any bytes have
        been exchanged. The protocol should be disconnected, but
        connectionLost should not be called re-entrantly.
        """
        self.runAbortTest(ProducerAbortingClient,
                          ConnectableProtocol)


    def test_resumeProducingAbortLater(self):
        """
        abortConnection() is called in resumeProducing, after some
        bytes have been exchanged. The protocol should be disconnected.
        """
        return self.runAbortTest(ProducerAbortingClientLater,
                                 AbortServerWritingProtocol)


    def test_fullWriteBuffer(self):
        """
        abortConnection() triggered by the write buffer being full.

        In particular, the server side stops reading. This is supposed
        to simulate a realistic timeout scenario where the client
        notices the server is no longer accepting data.

        The protocol should be disconnected, but connectionLost should not be
        called re-entrantly.
        """
        self.runAbortTest(StreamingProducerClient,
                          NoReadServer)


    def test_fullWriteBufferAfterByteExchange(self):
        """
        abortConnection() is triggered by a write buffer being full.

        However, this buffer is filled after some bytes have been exchanged,
        allowing a TLS handshake if we're testing TLS. The connection will
        then be lost.
        """
        return self.runAbortTest(StreamingProducerClientLater,
                                 EventualNoReadServer)


    def test_dataReceivedThrows(self):
        """
        dataReceived calls abortConnection(), and then raises an exception.

        The connection will be lost, with the thrown exception
        (C{ZeroDivisionError}) as the reason on the client. The idea here is
        that bugs should not be masked by abortConnection, in particular
        unexpected exceptions.
        """
        self.runAbortTest(DataReceivedRaisingClient,
                          AbortServerWritingProtocol,
                          clientConnectionLostReason=ZeroDivisionError)
        errors = self.flushLoggedErrors(ZeroDivisionError)
        self.assertEqual(len(errors), 1)


    def test_resumeProducingThrows(self):
        """
        resumeProducing calls abortConnection(), and then raises an exception.

        The connection will be lost, with the thrown exception
        (C{ZeroDivisionError}) as the reason on the client. The idea here is
        that bugs should not be masked by abortConnection, in particular
        unexpected exceptions.
        """
        self.runAbortTest(ResumeThrowsClient,
                          ConnectableProtocol,
                          clientConnectionLostReason=ZeroDivisionError)
        errors = self.flushLoggedErrors(ZeroDivisionError)
        self.assertEqual(len(errors), 1)



class AbortConnectionTests(ReactorBuilder, AbortConnectionMixin):
    """
    TCP-specific L{AbortConnectionMixin} tests.
    """
    requiredInterfaces = (IReactorTCP,)

    endpoints = TCPCreator()

globals().update(AbortConnectionTests.makeTestCaseClasses())



class SimpleUtilityTests(TestCase):
    """
    Simple, direct tests for helpers within L{twisted.internet.tcp}.
    """
    if ipv6Skip:
        skip = ipv6Skip

    def test_resolveNumericHost(self):
        """
        L{_resolveIPv6} raises a L{socket.gaierror} (L{socket.EAI_NONAME}) when
        invoked with a non-numeric host.  (In other words, it is passing
        L{socket.AI_NUMERICHOST} to L{socket.getaddrinfo} and will not
        accidentally block if it receives bad input.)
        """
        err = self.assertRaises(socket.gaierror, _resolveIPv6, "localhost", 1)
        self.assertEqual(err.args[0], socket.EAI_NONAME)


    def test_resolveNumericService(self):
        """
        L{_resolveIPv6} raises a L{socket.gaierror} (L{socket.EAI_NONAME}) when
        invoked with a non-numeric port.  (In other words, it is passing
        L{socket.AI_NUMERICSERV} to L{socket.getaddrinfo} and will not
        accidentally block if it receives bad input.)
        """
        err = self.assertRaises(socket.gaierror, _resolveIPv6, "::1", "http")
        self.assertEqual(err.args[0], socket.EAI_NONAME)

    if platform.isWindows():
        test_resolveNumericService.skip = ("The AI_NUMERICSERV flag is not "
                                           "supported by Microsoft providers.")
        # http://msdn.microsoft.com/en-us/library/windows/desktop/ms738520.aspx


    def test_resolveIPv6(self):
        """
        L{_resolveIPv6} discovers the flow info and scope ID of an IPv6
        address.
        """
        result = _resolveIPv6("::1", 2)
        self.assertEqual(len(result), 4)
        # We can't say anything more useful about these than that they're
        # integers, because the whole point of getaddrinfo is that you can never
        # know a-priori know _anything_ about the network interfaces of the
        # computer that you're on and you have to ask it.
        self.assertIsInstance(result[2], (int, long)) # flow info
        self.assertIsInstance(result[3], (int, long)) # scope id
        # but, luckily, IP presentation format and what it means to be a port
        # number are a little better specified.
        self.assertEqual(result[:2], ("::1", 2))
