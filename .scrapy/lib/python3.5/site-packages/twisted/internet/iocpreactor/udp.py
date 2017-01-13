# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
UDP support for IOCP reactor
"""

import socket, operator, struct, warnings, errno

from zope.interface import implementer

from twisted.internet import defer, address, error, interfaces
from twisted.internet.abstract import isIPAddress, isIPv6Address
from twisted.python import log, failure

from twisted.internet.iocpreactor.const import ERROR_IO_PENDING
from twisted.internet.iocpreactor.const import ERROR_CONNECTION_REFUSED
from twisted.internet.iocpreactor.const import ERROR_PORT_UNREACHABLE
from twisted.internet.iocpreactor.interfaces import IReadWriteHandle
from twisted.internet.iocpreactor import iocpsupport as _iocp, abstract



@implementer(IReadWriteHandle, interfaces.IListeningPort,
             interfaces.IUDPTransport, interfaces.ISystemHandle)
class Port(abstract.FileHandle):
    """
    UDP port, listening for packets.

    @ivar addressFamily: L{socket.AF_INET} or L{socket.AF_INET6}, depending on
        whether this port is listening on an IPv4 address or an IPv6 address.
    """
    addressFamily = socket.AF_INET
    socketType = socket.SOCK_DGRAM
    dynamicReadBuffers = False

    # Actual port number being listened on, only set to a non-None
    # value when we are actually listening.
    _realPortNumber = None


    def __init__(self, port, proto, interface='', maxPacketSize=8192,
                 reactor=None):
        """
        Initialize with a numeric port to listen on.
        """
        self.port = port
        self.protocol = proto
        self.readBufferSize = maxPacketSize
        self.interface = interface
        self.setLogStr()
        self._connectedAddr = None
        self._setAddressFamily()

        abstract.FileHandle.__init__(self, reactor)

        skt = socket.socket(self.addressFamily, self.socketType)
        addrLen = _iocp.maxAddrLen(skt.fileno())
        self.addressBuffer = bytearray(addrLen)
        # WSARecvFrom takes an int
        self.addressLengthBuffer = bytearray(struct.calcsize('i'))


    def _setAddressFamily(self):
        """
        Resolve address family for the socket.
        """
        if isIPv6Address(self.interface):
            self.addressFamily = socket.AF_INET6
        elif isIPAddress(self.interface):
            self.addressFamily = socket.AF_INET
        elif self.interface:
            raise error.InvalidAddressError(
                self.interface, 'not an IPv4 or IPv6 address')


    def __repr__(self):
        if self._realPortNumber is not None:
            return ("<%s on %s>" %
                    (self.protocol.__class__, self._realPortNumber))
        else:
            return "<%s not connected>" % (self.protocol.__class__,)


    def getHandle(self):
        """
        Return a socket object.
        """
        return self.socket


    def startListening(self):
        """
        Create and bind my socket, and begin listening on it.

        This is called on unserialization, and must be called after creating a
        server to begin listening on the specified port.
        """
        self._bindSocket()
        self._connectToProtocol()


    def createSocket(self):
        return self.reactor.createSocket(self.addressFamily, self.socketType)


    def _bindSocket(self):
        try:
            skt = self.createSocket()
            skt.bind((self.interface, self.port))
        except socket.error as le:
            raise error.CannotListenError(self.interface, self.port, le)

        # Make sure that if we listened on port 0, we update that to
        # reflect what the OS actually assigned us.
        self._realPortNumber = skt.getsockname()[1]

        log.msg("%s starting on %s" % (
                self._getLogPrefix(self.protocol), self._realPortNumber))

        self.connected = True
        self.socket = skt
        self.getFileHandle = self.socket.fileno


    def _connectToProtocol(self):
        self.protocol.makeConnection(self)
        self.startReading()
        self.reactor.addActiveHandle(self)


    def cbRead(self, rc, bytes, evt):
        if self.reading:
            self.handleRead(rc, bytes, evt)
            self.doRead()


    def handleRead(self, rc, bytes, evt):
        if rc in (errno.WSAECONNREFUSED, errno.WSAECONNRESET,
                  ERROR_CONNECTION_REFUSED, ERROR_PORT_UNREACHABLE):
            if self._connectedAddr:
                self.protocol.connectionRefused()
        elif rc:
            log.msg("error in recvfrom -- %s (%s)" %
                    (errno.errorcode.get(rc, 'unknown error'), rc))
        else:
            try:
                self.protocol.datagramReceived(str(evt.buff[:bytes]),
                    _iocp.makesockaddr(evt.addr_buff))
            except:
                log.err()


    def doRead(self):
        evt = _iocp.Event(self.cbRead, self)

        evt.buff = buff = self._readBuffers[0]
        evt.addr_buff = addr_buff = self.addressBuffer
        evt.addr_len_buff = addr_len_buff = self.addressLengthBuffer
        rc, bytes = _iocp.recvfrom(self.getFileHandle(), buff,
                                   addr_buff, addr_len_buff, evt)

        if rc and rc != ERROR_IO_PENDING:
            self.handleRead(rc, bytes, evt)


    def write(self, datagram, addr=None):
        """
        Write a datagram.

        @param addr: should be a tuple (ip, port), can be None in connected
        mode.
        """
        if self._connectedAddr:
            assert addr in (None, self._connectedAddr)
            try:
                return self.socket.send(datagram)
            except socket.error as se:
                no = se.args[0]
                if no == errno.WSAEINTR:
                    return self.write(datagram)
                elif no == errno.WSAEMSGSIZE:
                    raise error.MessageLengthError("message too long")
                elif no in (errno.WSAECONNREFUSED, errno.WSAECONNRESET,
                            ERROR_CONNECTION_REFUSED, ERROR_PORT_UNREACHABLE):
                    self.protocol.connectionRefused()
                else:
                    raise
        else:
            assert addr != None
            if (not isIPAddress(addr[0]) and not isIPv6Address(addr[0])
                    and addr[0] != "<broadcast>"):
                raise error.InvalidAddressError(
                    addr[0],
                    "write() only accepts IP addresses, not hostnames")
            if isIPAddress(addr[0]) and self.addressFamily == socket.AF_INET6:
                raise error.InvalidAddressError(
                    addr[0], "IPv6 port write() called with IPv4 address")
            if isIPv6Address(addr[0]) and self.addressFamily == socket.AF_INET:
                raise error.InvalidAddressError(
                    addr[0], "IPv4 port write() called with IPv6 address")
            try:
                return self.socket.sendto(datagram, addr)
            except socket.error as se:
                no = se.args[0]
                if no == errno.WSAEINTR:
                    return self.write(datagram, addr)
                elif no == errno.WSAEMSGSIZE:
                    raise error.MessageLengthError("message too long")
                elif no in (errno.WSAECONNREFUSED, errno.WSAECONNRESET,
                            ERROR_CONNECTION_REFUSED, ERROR_PORT_UNREACHABLE):
                    # in non-connected UDP ECONNREFUSED is platform dependent,
                    # I think and the info is not necessarily useful.
                    # Nevertheless maybe we should call connectionRefused? XXX
                    return
                else:
                    raise


    def writeSequence(self, seq, addr):
        self.write("".join(seq), addr)


    def connect(self, host, port):
        """
        'Connect' to remote server.
        """
        if self._connectedAddr:
            raise RuntimeError(
                "already connected, reconnecting is not currently supported "
                "(talk to itamar if you want this)")
        if not isIPAddress(host) and not isIPv6Address(host):
            raise error.InvalidAddressError(
                host, 'not an IPv4 or IPv6 address.')
        self._connectedAddr = (host, port)
        self.socket.connect((host, port))


    def _loseConnection(self):
        self.stopReading()
        self.reactor.removeActiveHandle(self)
        if self.connected: # actually means if we are *listening*
            self.reactor.callLater(0, self.connectionLost)


    def stopListening(self):
        if self.connected:
            result = self.d = defer.Deferred()
        else:
            result = None
        self._loseConnection()
        return result


    def loseConnection(self):
        warnings.warn("Please use stopListening() to disconnect port",
                      DeprecationWarning, stacklevel=2)
        self.stopListening()


    def connectionLost(self, reason=None):
        """
        Cleans up my socket.
        """
        log.msg('(UDP Port %s Closed)' % self._realPortNumber)
        self._realPortNumber = None
        abstract.FileHandle.connectionLost(self, reason)
        self.protocol.doStop()
        self.socket.close()
        del self.socket
        del self.getFileHandle
        if hasattr(self, "d"):
            self.d.callback(None)
            del self.d


    def setLogStr(self):
        """
        Initialize the C{logstr} attribute to be used by C{logPrefix}.
        """
        logPrefix = self._getLogPrefix(self.protocol)
        self.logstr = "%s (UDP)" % logPrefix


    def logPrefix(self):
        """
        Returns the name of my class, to prefix log entries with.
        """
        return self.logstr


    def getHost(self):
        """
        Return the local address of the UDP connection

        @returns: the local address of the UDP connection
        @rtype: L{IPv4Address} or L{IPv6Address}
        """
        addr = self.socket.getsockname()
        if self.addressFamily == socket.AF_INET:
            return address.IPv4Address('UDP', *addr)
        elif self.addressFamily == socket.AF_INET6:
            return address.IPv6Address('UDP', *(addr[:2]))


    def setBroadcastAllowed(self, enabled):
        """
        Set whether this port may broadcast. This is disabled by default.

        @param enabled: Whether the port may broadcast.
        @type enabled: L{bool}
        """
        self.socket.setsockopt(
            socket.SOL_SOCKET, socket.SO_BROADCAST, enabled)


    def getBroadcastAllowed(self):
        """
        Checks if broadcast is currently allowed on this port.

        @return: Whether this port may broadcast.
        @rtype: L{bool}
        """
        return operator.truth(
            self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST))



class MulticastMixin:
    """
    Implement multicast functionality.
    """


    def getOutgoingInterface(self):
        i = self.socket.getsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF)
        return socket.inet_ntoa(struct.pack("@i", i))


    def setOutgoingInterface(self, addr):
        """
        Returns Deferred of success.
        """
        return self.reactor.resolve(addr).addCallback(self._setInterface)


    def _setInterface(self, addr):
        i = socket.inet_aton(addr)
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, i)
        return 1


    def getLoopbackMode(self):
        return self.socket.getsockopt(socket.IPPROTO_IP,
                                      socket.IP_MULTICAST_LOOP)


    def setLoopbackMode(self, mode):
        mode = struct.pack("b", operator.truth(mode))
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP,
                               mode)


    def getTTL(self):
        return self.socket.getsockopt(socket.IPPROTO_IP,
                                      socket.IP_MULTICAST_TTL)


    def setTTL(self, ttl):
        ttl = struct.pack("B", ttl)
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)


    def joinGroup(self, addr, interface=""):
        """
        Join a multicast group. Returns Deferred of success.
        """
        return self.reactor.resolve(addr).addCallback(self._joinAddr1,
                                                      interface, 1)


    def _joinAddr1(self, addr, interface, join):
        return self.reactor.resolve(interface).addCallback(self._joinAddr2,
                                                           addr, join)


    def _joinAddr2(self, interface, addr, join):
        addr = socket.inet_aton(addr)
        interface = socket.inet_aton(interface)
        if join:
            cmd = socket.IP_ADD_MEMBERSHIP
        else:
            cmd = socket.IP_DROP_MEMBERSHIP
        try:
            self.socket.setsockopt(socket.IPPROTO_IP, cmd, addr + interface)
        except socket.error as e:
            return failure.Failure(error.MulticastJoinError(addr, interface,
                                                            *e.args))


    def leaveGroup(self, addr, interface=""):
        """
        Leave multicast group, return Deferred of success.
        """
        return self.reactor.resolve(addr).addCallback(self._joinAddr1,
                                                      interface, 0)



@implementer(interfaces.IMulticastTransport)
class MulticastPort(MulticastMixin, Port):
    """
    UDP Port that supports multicasting.
    """

    def __init__(self, port, proto, interface='', maxPacketSize=8192,
                 reactor=None, listenMultiple=False):
        Port.__init__(self, port, proto, interface, maxPacketSize, reactor)
        self.listenMultiple = listenMultiple


    def createSocket(self):
        skt = Port.createSocket(self)
        if self.listenMultiple:
            skt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                skt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        return skt
