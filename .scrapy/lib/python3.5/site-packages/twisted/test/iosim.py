# -*- test-case-name: twisted.test.test_amp,twisted.test.test_iosim -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Utilities and helpers for simulating a network
"""

from __future__ import absolute_import, division, print_function

import itertools

try:
    from OpenSSL.SSL import Error as NativeOpenSSLError
except ImportError:
    pass

from zope.interface import implementer, directlyProvides
from twisted.internet.endpoints import TCP4ClientEndpoint, TCP4ServerEndpoint
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.error import ConnectionRefusedError

from twisted.python.failure import Failure
from twisted.internet import error
from twisted.internet import interfaces

from .proto_helpers import MemoryReactorClock


class TLSNegotiation:
    def __init__(self, obj, connectState):
        self.obj = obj
        self.connectState = connectState
        self.sent = False
        self.readyToSend = connectState


    def __repr__(self):
        return 'TLSNegotiation(%r)' % (self.obj,)


    def pretendToVerify(self, other, tpt):
        # Set the transport problems list here?  disconnections?
        # hmmmmm... need some negative path tests.

        if not self.obj.iosimVerify(other.obj):
            tpt.disconnectReason = NativeOpenSSLError()
            tpt.loseConnection()



@implementer(interfaces.IAddress)
class FakeAddress(object):
    """
    The default address type for the host and peer of L{FakeTransport}
    connections.
    """



@implementer(interfaces.ITransport,
             interfaces.ITLSTransport)
class FakeTransport:
    """
    A wrapper around a file-like object to make it behave as a Transport.

    This doesn't actually stream the file to the attached protocol,
    and is thus useful mainly as a utility for debugging protocols.
    """

    _nextserial = staticmethod(lambda counter=itertools.count(): next(counter))
    closed = 0
    disconnecting = 0
    disconnected = 0
    disconnectReason = error.ConnectionDone("Connection done")
    producer = None
    streamingProducer = 0
    tls = None

    def __init__(self, protocol, isServer, hostAddress=None, peerAddress=None):
        """
        @param protocol: This transport will deliver bytes to this protocol.
        @type protocol: L{IProtocol} provider

        @param isServer: C{True} if this is the accepting side of the
            connection, C{False} if it is the connecting side.
        @type isServer: L{bool}

        @param hostAddress: The value to return from C{getHost}.  L{None}
            results in a new L{FakeAddress} being created to use as the value.
        @type hostAddress: L{IAddress} provider or L{None}

        @param peerAddress: The value to return from C{getPeer}.  L{None}
            results in a new L{FakeAddress} being created to use as the value.
        @type peerAddress: L{IAddress} provider or L{None}
        """
        self.protocol = protocol
        self.isServer = isServer
        self.stream = []
        self.serial = self._nextserial()
        if hostAddress is None:
            hostAddress = FakeAddress()
        self.hostAddress = hostAddress
        if peerAddress is None:
            peerAddress = FakeAddress()
        self.peerAddress = peerAddress


    def __repr__(self):
        return 'FakeTransport<%s,%s,%s>' % (
            self.isServer and 'S' or 'C', self.serial,
            self.protocol.__class__.__name__)


    def write(self, data):
        if self.tls is not None:
            self.tlsbuf.append(data)
        else:
            self.stream.append(data)


    def _checkProducer(self):
        # Cheating; this is called at "idle" times to allow producers to be
        # found and dealt with
        if self.producer:
            self.producer.resumeProducing()


    def registerProducer(self, producer, streaming):
        """
        From abstract.FileDescriptor
        """
        self.producer = producer
        self.streamingProducer = streaming
        if not streaming:
            producer.resumeProducing()


    def unregisterProducer(self):
        self.producer = None


    def stopConsuming(self):
        self.unregisterProducer()
        self.loseConnection()


    def writeSequence(self, iovec):
        self.write(b"".join(iovec))


    def loseConnection(self):
        self.disconnecting = True


    def abortConnection(self):
        """
        For the time being, this is the same as loseConnection; no buffered
        data will be lost.
        """
        self.disconnecting = True


    def reportDisconnect(self):
        if self.tls is not None:
            # We were in the middle of negotiating!  Must have been a TLS
            # problem.
            err = NativeOpenSSLError()
        else:
            err = self.disconnectReason
        self.protocol.connectionLost(Failure(err))


    def logPrefix(self):
        """
        Identify this transport/event source to the logging system.
        """
        return "iosim"


    def getPeer(self):
        return self.peerAddress


    def getHost(self):
        return self.hostAddress


    def resumeProducing(self):
        # Never sends data anyways
        pass


    def pauseProducing(self):
        # Never sends data anyways
        pass


    def stopProducing(self):
        self.loseConnection()


    def startTLS(self, contextFactory, beNormal=True):
        # Nothing's using this feature yet, but startTLS has an undocumented
        # second argument which defaults to true; if set to False, servers will
        # behave like clients and clients will behave like servers.
        connectState = self.isServer ^ beNormal
        self.tls = TLSNegotiation(contextFactory, connectState)
        self.tlsbuf = []


    def getOutBuffer(self):
        """
        Get the pending writes from this transport, clearing them from the
        pending buffer.

        @return: the bytes written with C{transport.write}
        @rtype: L{bytes}
        """
        S = self.stream
        if S:
            self.stream = []
            return b''.join(S)
        elif self.tls is not None:
            if self.tls.readyToSend:
                # Only _send_ the TLS negotiation "packet" if I'm ready to.
                self.tls.sent = True
                return self.tls
            else:
                return None
        else:
            return None


    def bufferReceived(self, buf):
        if isinstance(buf, TLSNegotiation):
            assert self.tls is not None # By the time you're receiving a
                                        # negotiation, you have to have called
                                        # startTLS already.
            if self.tls.sent:
                self.tls.pretendToVerify(buf, self)
                self.tls = None # We're done with the handshake if we've gotten
                                # this far... although maybe it failed...?
                # TLS started!  Unbuffer...
                b, self.tlsbuf = self.tlsbuf, None
                self.writeSequence(b)
                directlyProvides(self, interfaces.ISSLTransport)
            else:
                # We haven't sent our own TLS negotiation: time to do that!
                self.tls.readyToSend = True
        else:
            self.protocol.dataReceived(buf)



def makeFakeClient(clientProtocol):
    """
    Create and return a new in-memory transport hooked up to the given protocol.

    @param clientProtocol: The client protocol to use.
    @type clientProtocol: L{IProtocol} provider

    @return: The transport.
    @rtype: L{FakeTransport}
    """
    return FakeTransport(clientProtocol, isServer=False)



def makeFakeServer(serverProtocol):
    """
    Create and return a new in-memory transport hooked up to the given protocol.

    @param serverProtocol: The server protocol to use.
    @type serverProtocol: L{IProtocol} provider

    @return: The transport.
    @rtype: L{FakeTransport}
    """
    return FakeTransport(serverProtocol, isServer=True)



class IOPump:
    """
    Utility to pump data between clients and servers for protocol testing.

    Perhaps this is a utility worthy of being in protocol.py?
    """
    def __init__(self, client, server, clientIO, serverIO, debug):
        self.client = client
        self.server = server
        self.clientIO = clientIO
        self.serverIO = serverIO
        self.debug = debug


    def flush(self, debug=False):
        """
        Pump until there is no more input or output.

        Returns whether any data was moved.
        """
        result = False
        for x in range(1000):
            if self.pump(debug):
                result = True
            else:
                break
        else:
            assert 0, "Too long"
        return result


    def pump(self, debug=False):
        """
        Move data back and forth.

        Returns whether any data was moved.
        """
        if self.debug or debug:
            print('-- GLUG --')
        sData = self.serverIO.getOutBuffer()
        cData = self.clientIO.getOutBuffer()
        self.clientIO._checkProducer()
        self.serverIO._checkProducer()
        if self.debug or debug:
            print('.')
            # XXX slightly buggy in the face of incremental output
            if cData:
                print('C: ' + repr(cData))
            if sData:
                print('S: ' + repr(sData))
        if cData:
            self.serverIO.bufferReceived(cData)
        if sData:
            self.clientIO.bufferReceived(sData)
        if cData or sData:
            return True
        if (self.serverIO.disconnecting and
            not self.serverIO.disconnected):
            if self.debug or debug:
                print('* C')
            self.serverIO.disconnected = True
            self.clientIO.disconnecting = True
            self.clientIO.reportDisconnect()
            return True
        if self.clientIO.disconnecting and not self.clientIO.disconnected:
            if self.debug or debug:
                print('* S')
            self.clientIO.disconnected = True
            self.serverIO.disconnecting = True
            self.serverIO.reportDisconnect()
            return True
        return False



def connect(serverProtocol, serverTransport, clientProtocol, clientTransport,
            debug=False, greet=True):
    """
    Create a new L{IOPump} connecting two protocols.

    @param serverProtocol: The protocol to use on the accepting side of the
        connection.
    @type serverProtocol: L{IProtocol} provider

    @param serverTransport: The transport to associate with C{serverProtocol}.
    @type serverTransport: L{FakeTransport}

    @param clientProtocol: The protocol to use on the initiating side of the
        connection.
    @type clientProtocol: L{IProtocol} provider

    @param clientTransport: The transport to associate with C{clientProtocol}.
    @type clientTransport: L{FakeTransport}

    @param debug: A flag indicating whether to log information about what the
        L{IOPump} is doing.
    @type debug: L{bool}

    @param greet: Should the L{IOPump} be L{flushed <IOPump.flush>} once before
        returning to put the protocols into their post-handshake or
        post-server-greeting state?
    @type greet: L{bool}

    @return: An L{IOPump} which connects C{serverProtocol} and
        C{clientProtocol} and delivers bytes between them when it is pumped.
    @rtype: L{IOPump}
    """
    serverProtocol.makeConnection(serverTransport)
    clientProtocol.makeConnection(clientTransport)
    pump = IOPump(
        clientProtocol, serverProtocol, clientTransport, serverTransport, debug
    )
    if greet:
        # Kick off server greeting, etc
        pump.flush()
    return pump



def connectedServerAndClient(ServerClass, ClientClass,
                             clientTransportFactory=makeFakeClient,
                             serverTransportFactory=makeFakeServer,
                             debug=False, greet=True):
    """
    Connect a given server and client class to each other.

    @param ServerClass: a callable that produces the server-side protocol.
    @type ServerClass: 0-argument callable returning L{IProtocol} provider.

    @param ClientClass: like C{ServerClass} but for the other side of the
        connection.
    @type ClientClass: 0-argument callable returning L{IProtocol} provider.

    @param clientTransportFactory: a callable that produces the transport which
        will be attached to the protocol returned from C{ClientClass}.
    @type clientTransportFactory: callable taking (L{IProtocol}) and returning
        L{FakeTransport}

    @param serverTransportFactory: a callable that produces the transport which
        will be attached to the protocol returned from C{ServerClass}.
    @type serverTransportFactory: callable taking (L{IProtocol}) and returning
        L{FakeTransport}

    @param debug: Should this dump an escaped version of all traffic on this
        connection to stdout for inspection?
    @type debug: L{bool}

    @param greet: Should the L{IOPump} be L{flushed <IOPump.flush>} once before
        returning to put the protocols into their post-handshake or
        post-server-greeting state?
    @type greet: L{bool}

    @return: the client protocol, the server protocol, and an L{IOPump} which,
        when its C{pump} and C{flush} methods are called, will move data
        between the created client and server protocol instances.
    @rtype: 3-L{tuple} of L{IProtocol}, L{IProtocol}, L{IOPump}
    """
    c = ClientClass()
    s = ServerClass()
    cio = clientTransportFactory(c)
    sio = serverTransportFactory(s)
    return c, s, connect(s, sio, c, cio, debug, greet)



def _factoriesShouldConnect(clientInfo, serverInfo):
    """
    Should the client and server described by the arguments be connected to
    each other, i.e. do their port numbers match?

    @param clientInfo: the args for connectTCP
    @type clientInfo: L{tuple}

    @param serverInfo: the args for listenTCP
    @type serverInfo: L{tuple}

    @return: If they do match, return factories for the client and server that
        should connect; otherwise return L{None}, indicating they shouldn't be
        connected.
    @rtype: L{None} or 2-L{tuple} of (L{ClientFactory},
        L{IProtocolFactory})
    """
    (clientHost, clientPort, clientFactory, clientTimeout,
     clientBindAddress) = clientInfo
    (serverPort, serverFactory, serverBacklog,
     serverInterface) = serverInfo
    if serverPort == clientPort:
        return clientFactory, serverFactory
    else:
        return None



class ConnectionCompleter(object):
    """
    A L{ConnectionCompleter} can cause synthetic TCP connections established by
    L{MemoryReactor.connectTCP} and L{MemoryReactor.listenTCP} to succeed or
    fail.
    """
    def __init__(self, memoryReactor):
        """
        Create a L{ConnectionCompleter} from a L{MemoryReactor}.

        @param memoryReactor: The reactor to attach to.
        @type memoryReactor: L{MemoryReactor}
        """
        self._reactor = memoryReactor


    def succeedOnce(self, debug=False):
        """
        Complete a single TCP connection established on this
        L{ConnectionCompleter}'s L{MemoryReactor}.

        @param debug: A flag; whether to dump output from the established
            connection to stdout.
        @type debug: L{bool}

        @return: a pump for the connection, or L{None} if no connection could
            be established.
        @rtype: L{IOPump} or L{None}
        """
        memoryReactor = self._reactor
        for clientIdx, clientInfo in enumerate(memoryReactor.tcpClients):
            for serverInfo in memoryReactor.tcpServers:
                factories = _factoriesShouldConnect(clientInfo, serverInfo)
                if factories:
                    memoryReactor.tcpClients.remove(clientInfo)
                    memoryReactor.connectors.pop(clientIdx)
                    clientFactory, serverFactory = factories
                    clientProtocol = clientFactory.buildProtocol(None)
                    serverProtocol = serverFactory.buildProtocol(None)
                    serverTransport = makeFakeServer(serverProtocol)
                    clientTransport = makeFakeClient(clientProtocol)
                    return connect(serverProtocol, serverTransport,
                                   clientProtocol, clientTransport,
                                   debug)


    def failOnce(self, reason=Failure(ConnectionRefusedError())):
        """
        Fail a single TCP connection established on this
        L{ConnectionCompleter}'s L{MemoryReactor}.

        @param reason: the reason to provide that the connection failed.
        @type reason: L{Failure}
        """
        self._reactor.tcpClients.pop(0)[2].clientConnectionFailed(
            self._reactor.connectors.pop(0), reason
        )



def connectableEndpoint(debug=False):
    """
    Create an endpoint that can be fired on demand.

    @param debug: A flag; whether to dump output from the established
        connection to stdout.
    @type debug: L{bool}

    @return: A client endpoint, and an object that will cause one of the
        L{Deferred}s returned by that client endpoint.
    @rtype: 2-L{tuple} of (L{IStreamClientEndpoint}, L{ConnectionCompleter})
    """
    reactor = MemoryReactorClock()
    clientEndpoint = TCP4ClientEndpoint(reactor, "0.0.0.0", 4321)
    serverEndpoint = TCP4ServerEndpoint(reactor, 4321)
    serverEndpoint.listen(Factory.forProtocol(Protocol))
    return clientEndpoint, ConnectionCompleter(reactor)
