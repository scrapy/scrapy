# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
TCP support for IOCP reactor
"""

import socket, operator, errno, struct

from zope.interface import implementer, classImplements

from twisted.internet import interfaces, error, address, main, defer
from twisted.internet.protocol import Protocol
from twisted.internet.abstract import _LogOwner, isIPv6Address
from twisted.internet.tcp import _SocketCloser, Connector as TCPConnector
from twisted.internet.tcp import _AbortingMixin, _BaseBaseClient, _BaseTCPClient
from twisted.python import log, failure, reflect

from twisted.internet.iocpreactor import iocpsupport as _iocp, abstract
from twisted.internet.iocpreactor.interfaces import IReadWriteHandle
from twisted.internet.iocpreactor.const import ERROR_IO_PENDING
from twisted.internet.iocpreactor.const import SO_UPDATE_CONNECT_CONTEXT
from twisted.internet.iocpreactor.const import SO_UPDATE_ACCEPT_CONTEXT
from twisted.internet.iocpreactor.const import ERROR_CONNECTION_REFUSED
from twisted.internet.iocpreactor.const import ERROR_NETWORK_UNREACHABLE

try:
    from twisted.internet._newtls import startTLS as _startTLS
except ImportError:
    _startTLS = None

# ConnectEx returns these. XXX: find out what it does for timeout
connectExErrors = {
        ERROR_CONNECTION_REFUSED: errno.WSAECONNREFUSED,
        ERROR_NETWORK_UNREACHABLE: errno.WSAENETUNREACH,
        }

@implementer(IReadWriteHandle, interfaces.ITCPTransport,
             interfaces.ISystemHandle)
class Connection(abstract.FileHandle, _SocketCloser, _AbortingMixin):
    """
    @ivar TLS: C{False} to indicate the connection is in normal TCP mode,
        C{True} to indicate that TLS has been started and that operations must
        be routed through the L{TLSMemoryBIOProtocol} instance.
    """
    TLS = False


    def __init__(self, sock, proto, reactor=None):
        abstract.FileHandle.__init__(self, reactor)
        self.socket = sock
        self.getFileHandle = sock.fileno
        self.protocol = proto


    def getHandle(self):
        return self.socket


    def dataReceived(self, rbuffer):
        # XXX: some day, we'll have protocols that can handle raw buffers
        self.protocol.dataReceived(str(rbuffer))


    def readFromHandle(self, bufflist, evt):
        return _iocp.recv(self.getFileHandle(), bufflist, evt)


    def writeToHandle(self, buff, evt):
        """
        Send C{buff} to current file handle using C{_iocp.send}. The buffer
        sent is limited to a size of C{self.SEND_LIMIT}.
        """
        return _iocp.send(self.getFileHandle(),
            buffer(buff, 0, self.SEND_LIMIT), evt)


    def _closeWriteConnection(self):
        try:
            self.socket.shutdown(1)
        except socket.error:
            pass
        p = interfaces.IHalfCloseableProtocol(self.protocol, None)
        if p:
            try:
                p.writeConnectionLost()
            except:
                f = failure.Failure()
                log.err()
                self.connectionLost(f)


    def readConnectionLost(self, reason):
        p = interfaces.IHalfCloseableProtocol(self.protocol, None)
        if p:
            try:
                p.readConnectionLost()
            except:
                log.err()
                self.connectionLost(failure.Failure())
        else:
            self.connectionLost(reason)


    def connectionLost(self, reason):
        if self.disconnected:
            return
        abstract.FileHandle.connectionLost(self, reason)
        isClean = (reason is None or
                   not reason.check(error.ConnectionAborted))
        self._closeSocket(isClean)
        protocol = self.protocol
        del self.protocol
        del self.socket
        del self.getFileHandle
        protocol.connectionLost(reason)


    def logPrefix(self):
        """
        Return the prefix to log with when I own the logging thread.
        """
        return self.logstr


    def getTcpNoDelay(self):
        return operator.truth(self.socket.getsockopt(socket.IPPROTO_TCP,
                                                     socket.TCP_NODELAY))


    def setTcpNoDelay(self, enabled):
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, enabled)


    def getTcpKeepAlive(self):
        return operator.truth(self.socket.getsockopt(socket.SOL_SOCKET,
                                                     socket.SO_KEEPALIVE))


    def setTcpKeepAlive(self, enabled):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, enabled)


    if _startTLS is not None:
        def startTLS(self, contextFactory, normal=True):
            """
            @see: L{ITLSTransport.startTLS}
            """
            _startTLS(self, contextFactory, normal, abstract.FileHandle)


    def write(self, data):
        """
        Write some data, either directly to the underlying handle or, if TLS
        has been started, to the L{TLSMemoryBIOProtocol} for it to encrypt and
        send.

        @see: L{twisted.internet.interfaces.ITransport.write}
        """
        if self.disconnected:
            return
        if self.TLS:
            self.protocol.write(data)
        else:
            abstract.FileHandle.write(self, data)


    def writeSequence(self, iovec):
        """
        Write some data, either directly to the underlying handle or, if TLS
        has been started, to the L{TLSMemoryBIOProtocol} for it to encrypt and
        send.

        @see: L{twisted.internet.interfaces.ITransport.writeSequence}
        """
        if self.disconnected:
            return
        if self.TLS:
            self.protocol.writeSequence(iovec)
        else:
            abstract.FileHandle.writeSequence(self, iovec)


    def loseConnection(self, reason=None):
        """
        Close the underlying handle or, if TLS has been started, first shut it
        down.

        @see: L{twisted.internet.interfaces.ITransport.loseConnection}
        """
        if self.TLS:
            if self.connected and not self.disconnecting:
                self.protocol.loseConnection()
        else:
            abstract.FileHandle.loseConnection(self, reason)


    def registerProducer(self, producer, streaming):
        """
        Register a producer.

        If TLS is enabled, the TLS connection handles this.
        """
        if self.TLS:
            # Registering a producer before we're connected shouldn't be a
            # problem. If we end up with a write(), that's already handled in
            # the write() code above, and there are no other potential
            # side-effects.
            self.protocol.registerProducer(producer, streaming)
        else:
            abstract.FileHandle.registerProducer(self, producer, streaming)


    def unregisterProducer(self):
        """
        Unregister a producer.

        If TLS is enabled, the TLS connection handles this.
        """
        if self.TLS:
            self.protocol.unregisterProducer()
        else:
            abstract.FileHandle.unregisterProducer(self)

if _startTLS is not None:
    classImplements(Connection, interfaces.ITLSTransport)



class Client(_BaseBaseClient, _BaseTCPClient, Connection):
    """
    @ivar _tlsClientDefault: Always C{True}, indicating that this is a client
        connection, and by default when TLS is negotiated this class will act as
        a TLS client.
    """
    addressFamily = socket.AF_INET
    socketType = socket.SOCK_STREAM

    _tlsClientDefault = True
    _commonConnection = Connection

    def __init__(self, host, port, bindAddress, connector, reactor):
        # ConnectEx documentation says socket _has_ to be bound
        if bindAddress is None:
            bindAddress = ('', 0)
        self.reactor = reactor # createInternetSocket needs this
        _BaseTCPClient.__init__(self, host, port, bindAddress, connector,
                                reactor)


    def createInternetSocket(self):
        """
        Create a socket registered with the IOCP reactor.

        @see: L{_BaseTCPClient}
        """
        return self.reactor.createSocket(self.addressFamily, self.socketType)


    def _collectSocketDetails(self):
        """
        Clean up potentially circular references to the socket and to its
        C{getFileHandle} method.

        @see: L{_BaseBaseClient}
        """
        del self.socket, self.getFileHandle


    def _stopReadingAndWriting(self):
        """
        Remove the active handle from the reactor.

        @see: L{_BaseBaseClient}
        """
        self.reactor.removeActiveHandle(self)


    def cbConnect(self, rc, bytes, evt):
        if rc:
            rc = connectExErrors.get(rc, rc)
            self.failIfNotConnected(error.getConnectError((rc,
                                    errno.errorcode.get(rc, 'Unknown error'))))
        else:
            self.socket.setsockopt(
                socket.SOL_SOCKET, SO_UPDATE_CONNECT_CONTEXT,
                struct.pack('P', self.socket.fileno()))
            self.protocol = self.connector.buildProtocol(self.getPeer())
            self.connected = True
            logPrefix = self._getLogPrefix(self.protocol)
            self.logstr = logPrefix + ",client"
            if self.protocol is None:
                # Factory.buildProtocol is allowed to return None.  In that
                # case, make up a protocol to satisfy the rest of the
                # implementation; connectionLost is going to be called on
                # something, for example.  This is easier than adding special
                # case support for a None protocol throughout the rest of the
                # transport implementation.
                self.protocol = Protocol()
                # But dispose of the connection quickly.
                self.loseConnection()
            else:
                self.protocol.makeConnection(self)
                self.startReading()


    def doConnect(self):
        if not hasattr(self, "connector"):
            # this happens if we connector.stopConnecting in
            # factory.startedConnecting
            return
        assert _iocp.have_connectex
        self.reactor.addActiveHandle(self)
        evt = _iocp.Event(self.cbConnect, self)

        rc = _iocp.connect(self.socket.fileno(), self.realAddress, evt)
        if rc and rc != ERROR_IO_PENDING:
            self.cbConnect(rc, 0, evt)



class Server(Connection):
    """
    Serverside socket-stream connection class.

    I am a serverside network connection transport; a socket which came from an
    accept() on a server.

    @ivar _tlsClientDefault: Always C{False}, indicating that this is a server
        connection, and by default when TLS is negotiated this class will act as
        a TLS server.
    """

    _tlsClientDefault = False


    def __init__(self, sock, protocol, clientAddr, serverAddr, sessionno, reactor):
        """
        Server(sock, protocol, client, server, sessionno)

        Initialize me with a socket, a protocol, a descriptor for my peer (a
        tuple of host, port describing the other end of the connection), an
        instance of Port, and a session number.
        """
        Connection.__init__(self, sock, protocol, reactor)
        self.serverAddr = serverAddr
        self.clientAddr = clientAddr
        self.sessionno = sessionno
        logPrefix = self._getLogPrefix(self.protocol)
        self.logstr = "%s,%s,%s" % (logPrefix, sessionno, self.clientAddr.host)
        self.repstr = "<%s #%s on %s>" % (self.protocol.__class__.__name__,
                                          self.sessionno, self.serverAddr.port)
        self.connected = True
        self.startReading()


    def __repr__(self):
        """
        A string representation of this connection.
        """
        return self.repstr


    def getHost(self):
        """
        Returns an IPv4Address.

        This indicates the server's address.
        """
        return self.serverAddr


    def getPeer(self):
        """
        Returns an IPv4Address.

        This indicates the client's address.
        """
        return self.clientAddr



class Connector(TCPConnector):
    def _makeTransport(self):
        return Client(self.host, self.port, self.bindAddress, self,
                      self.reactor)



@implementer(interfaces.IListeningPort)
class Port(_SocketCloser, _LogOwner):

    connected = False
    disconnected = False
    disconnecting = False
    addressFamily = socket.AF_INET
    socketType = socket.SOCK_STREAM
    _addressType = address.IPv4Address
    sessionno = 0

    # Actual port number being listened on, only set to a non-None
    # value when we are actually listening.
    _realPortNumber = None

    # A string describing the connections which will be created by this port.
    # Normally this is C{"TCP"}, since this is a TCP port, but when the TLS
    # implementation re-uses this class it overrides the value with C{"TLS"}.
    # Only used for logging.
    _type = 'TCP'

    def __init__(self, port, factory, backlog=50, interface='', reactor=None):
        self.port = port
        self.factory = factory
        self.backlog = backlog
        self.interface = interface
        self.reactor = reactor
        if isIPv6Address(interface):
            self.addressFamily = socket.AF_INET6
            self._addressType = address.IPv6Address


    def __repr__(self):
        if self._realPortNumber is not None:
            return "<%s of %s on %s>" % (self.__class__,
                                         self.factory.__class__,
                                         self._realPortNumber)
        else:
            return "<%s of %s (not listening)>" % (self.__class__,
                                                   self.factory.__class__)


    def startListening(self):
        try:
            skt = self.reactor.createSocket(self.addressFamily,
                                            self.socketType)
            # TODO: resolve self.interface if necessary
            if self.addressFamily == socket.AF_INET6:
                addr = socket.getaddrinfo(self.interface, self.port)[0][4]
            else:
                addr = (self.interface, self.port)
            skt.bind(addr)
        except socket.error as le:
            raise error.CannotListenError(self.interface, self.port, le)

        self.addrLen = _iocp.maxAddrLen(skt.fileno())

        # Make sure that if we listened on port 0, we update that to
        # reflect what the OS actually assigned us.
        self._realPortNumber = skt.getsockname()[1]

        log.msg("%s starting on %s" % (self._getLogPrefix(self.factory),
                                       self._realPortNumber))

        self.factory.doStart()
        skt.listen(self.backlog)
        self.connected = True
        self.disconnected = False
        self.reactor.addActiveHandle(self)
        self.socket = skt
        self.getFileHandle = self.socket.fileno
        self.doAccept()


    def loseConnection(self, connDone=failure.Failure(main.CONNECTION_DONE)):
        """
        Stop accepting connections on this port.

        This will shut down my socket and call self.connectionLost().
        It returns a deferred which will fire successfully when the
        port is actually closed.
        """
        self.disconnecting = True
        if self.connected:
            self.deferred = defer.Deferred()
            self.reactor.callLater(0, self.connectionLost, connDone)
            return self.deferred

    stopListening = loseConnection


    def _logConnectionLostMsg(self):
        """
        Log message for closing port
        """
        log.msg('(%s Port %s Closed)' % (self._type, self._realPortNumber))


    def connectionLost(self, reason):
        """
        Cleans up the socket.
        """
        self._logConnectionLostMsg()
        self._realPortNumber = None
        d = None
        if hasattr(self, "deferred"):
            d = self.deferred
            del self.deferred

        self.disconnected = True
        self.reactor.removeActiveHandle(self)
        self.connected = False
        self._closeSocket(True)
        del self.socket
        del self.getFileHandle

        try:
            self.factory.doStop()
        except:
            self.disconnecting = False
            if d is not None:
                d.errback(failure.Failure())
            else:
                raise
        else:
            self.disconnecting = False
            if d is not None:
                d.callback(None)


    def logPrefix(self):
        """
        Returns the name of my class, to prefix log entries with.
        """
        return reflect.qual(self.factory.__class__)


    def getHost(self):
        """
        Returns an IPv4Address.

        This indicates the server's address.
        """
        host, port = self.socket.getsockname()[:2]
        return self._addressType('TCP', host, port)


    def cbAccept(self, rc, bytes, evt):
        self.handleAccept(rc, evt)
        if not (self.disconnecting or self.disconnected):
            self.doAccept()


    def handleAccept(self, rc, evt):
        if self.disconnecting or self.disconnected:
            return False

        # possible errors:
        # (WSAEMFILE, WSAENOBUFS, WSAENFILE, WSAENOMEM, WSAECONNABORTED)
        if rc:
            log.msg("Could not accept new connection -- %s (%s)" %
                    (errno.errorcode.get(rc, 'unknown error'), rc))
            return False
        else:
            evt.newskt.setsockopt(
                socket.SOL_SOCKET, SO_UPDATE_ACCEPT_CONTEXT,
                struct.pack('P', self.socket.fileno()))
            family, lAddr, rAddr = _iocp.get_accept_addrs(evt.newskt.fileno(),
                                                          evt.buff)
            assert family == self.addressFamily

            protocol = self.factory.buildProtocol(
                self._addressType('TCP', rAddr[0], rAddr[1]))
            if protocol is None:
                evt.newskt.close()
            else:
                s = self.sessionno
                self.sessionno = s+1
                transport = Server(evt.newskt, protocol,
                        self._addressType('TCP', rAddr[0], rAddr[1]),
                        self._addressType('TCP', lAddr[0], lAddr[1]),
                        s, self.reactor)
                protocol.makeConnection(transport)
            return True


    def doAccept(self):
        evt = _iocp.Event(self.cbAccept, self)

        # see AcceptEx documentation
        evt.buff = buff = bytearray(2 * (self.addrLen + 16))

        evt.newskt = newskt = self.reactor.createSocket(self.addressFamily,
                                                        self.socketType)
        rc = _iocp.accept(self.socket.fileno(), newskt.fileno(), buff, evt)

        if rc and rc != ERROR_IO_PENDING:
            self.handleAccept(rc, evt)
