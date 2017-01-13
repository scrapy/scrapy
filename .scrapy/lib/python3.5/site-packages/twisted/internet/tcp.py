# -*- test-case-name: twisted.test.test_tcp -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Various asynchronous TCP/IP classes.

End users shouldn't use this module directly - use the reactor APIs instead.
"""

from __future__ import division, absolute_import

# System Imports
import socket
import sys
import operator
import struct

from zope.interface import implementer

from twisted.python.compat import _PY3, lazyByteSlice
from twisted.python.runtime import platformType
from twisted.python import versions, deprecate

try:
    # Try to get the memory BIO based startTLS implementation, available since
    # pyOpenSSL 0.10
    from twisted.internet._newtls import (
        ConnectionMixin as _TLSConnectionMixin,
        ClientMixin as _TLSClientMixin,
        ServerMixin as _TLSServerMixin)
except ImportError:
    # There is no version of startTLS available
    class _TLSConnectionMixin(object):
        TLS = False


    class _TLSClientMixin(object):
        pass


    class _TLSServerMixin(object):
        pass


if platformType == 'win32':
    # no such thing as WSAEPERM or error code 10001 according to winsock.h or MSDN
    EPERM = object()
    from errno import WSAEINVAL as EINVAL
    from errno import WSAEWOULDBLOCK as EWOULDBLOCK
    from errno import WSAEINPROGRESS as EINPROGRESS
    from errno import WSAEALREADY as EALREADY
    from errno import WSAEISCONN as EISCONN
    from errno import WSAENOBUFS as ENOBUFS
    from errno import WSAEMFILE as EMFILE
    # No such thing as WSAENFILE, either.
    ENFILE = object()
    # Nor ENOMEM
    ENOMEM = object()
    EAGAIN = EWOULDBLOCK
    from errno import WSAECONNRESET as ECONNABORTED

    from twisted.python.win32 import formatError as strerror
else:
    from errno import EPERM
    from errno import EINVAL
    from errno import EWOULDBLOCK
    from errno import EINPROGRESS
    from errno import EALREADY
    from errno import EISCONN
    from errno import ENOBUFS
    from errno import EMFILE
    from errno import ENFILE
    from errno import ENOMEM
    from errno import EAGAIN
    from errno import ECONNABORTED

    from os import strerror


from errno import errorcode

# Twisted Imports
from twisted.internet import base, address, fdesc
from twisted.internet.task import deferLater
from twisted.python import log, failure, reflect
from twisted.python.util import untilConcludes
from twisted.internet.error import CannotListenError
from twisted.internet import abstract, main, interfaces, error
from twisted.internet.protocol import Protocol

# Not all platforms have, or support, this flag.
_AI_NUMERICSERV = getattr(socket, "AI_NUMERICSERV", 0)


# The type for service names passed to socket.getservbyname:
if _PY3:
    _portNameType = str
else:
    _portNameType = (str, unicode)



class _SocketCloser(object):
    """
    @ivar _shouldShutdown: Set to C{True} if C{shutdown} should be called
        before calling C{close} on the underlying socket.
    @type _shouldShutdown: C{bool}
    """
    _shouldShutdown = True

    def _closeSocket(self, orderly):
        # The call to shutdown() before close() isn't really necessary, because
        # we set FD_CLOEXEC now, which will ensure this is the only process
        # holding the FD, thus ensuring close() really will shutdown the TCP
        # socket. However, do it anyways, just to be safe.
        skt = self.socket
        try:
            if orderly:
                if self._shouldShutdown:
                    skt.shutdown(2)
            else:
                # Set SO_LINGER to 1,0 which, by convention, causes a
                # connection reset to be sent when close is called,
                # instead of the standard FIN shutdown sequence.
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                       struct.pack("ii", 1, 0))

        except socket.error:
            pass
        try:
            skt.close()
        except socket.error:
            pass



class _AbortingMixin(object):
    """
    Common implementation of C{abortConnection}.

    @ivar _aborting: Set to C{True} when C{abortConnection} is called.
    @type _aborting: C{bool}
    """
    _aborting = False

    def abortConnection(self):
        """
        Aborts the connection immediately, dropping any buffered data.

        @since: 11.1
        """
        if self.disconnected or self._aborting:
            return
        self._aborting = True
        self.stopReading()
        self.stopWriting()
        self.doRead = lambda *args, **kwargs: None
        self.doWrite = lambda *args, **kwargs: None
        self.reactor.callLater(0, self.connectionLost,
                               failure.Failure(error.ConnectionAborted()))



@implementer(interfaces.ITCPTransport, interfaces.ISystemHandle)
class Connection(_TLSConnectionMixin, abstract.FileDescriptor, _SocketCloser,
                 _AbortingMixin):
    """
    Superclass of all socket-based FileDescriptors.

    This is an abstract superclass of all objects which represent a TCP/IP
    connection based socket.

    @ivar logstr: prefix used when logging events related to this connection.
    @type logstr: C{str}
    """


    def __init__(self, skt, protocol, reactor=None):
        abstract.FileDescriptor.__init__(self, reactor=reactor)
        self.socket = skt
        self.socket.setblocking(0)
        self.fileno = skt.fileno
        self.protocol = protocol


    def getHandle(self):
        """Return the socket for this connection."""
        return self.socket


    def doRead(self):
        """Calls self.protocol.dataReceived with all available data.

        This reads up to self.bufferSize bytes of data from its socket, then
        calls self.dataReceived(data) to process it.  If the connection is not
        lost through an error in the physical recv(), this function will return
        the result of the dataReceived call.
        """
        try:
            data = self.socket.recv(self.bufferSize)
        except socket.error as se:
            if se.args[0] == EWOULDBLOCK:
                return
            else:
                return main.CONNECTION_LOST

        return self._dataReceived(data)


    def _dataReceived(self, data):
        if not data:
            return main.CONNECTION_DONE
        rval = self.protocol.dataReceived(data)
        if rval is not None:
            offender = self.protocol.dataReceived
            warningFormat = (
                'Returning a value other than None from %(fqpn)s is '
                'deprecated since %(version)s.')
            warningString = deprecate.getDeprecationWarningString(
                offender, versions.Version('Twisted', 11, 0, 0),
                format=warningFormat)
            deprecate.warnAboutFunction(offender, warningString)
        return rval


    def writeSomeData(self, data):
        """
        Write as much as possible of the given data to this TCP connection.

        This sends up to C{self.SEND_LIMIT} bytes from C{data}.  If the
        connection is lost, an exception is returned.  Otherwise, the number
        of bytes successfully written is returned.
        """
        # Limit length of buffer to try to send, because some OSes are too
        # stupid to do so themselves (ahem windows)
        limitedData = lazyByteSlice(data, 0, self.SEND_LIMIT)

        try:
            return untilConcludes(self.socket.send, limitedData)
        except socket.error as se:
            if se.args[0] in (EWOULDBLOCK, ENOBUFS):
                return 0
            else:
                return main.CONNECTION_LOST


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
        """See abstract.FileDescriptor.connectionLost().
        """
        # Make sure we're not called twice, which can happen e.g. if
        # abortConnection() is called from protocol's dataReceived and then
        # code immediately after throws an exception that reaches the
        # reactor. We can't rely on "disconnected" attribute for this check
        # since twisted.internet._oldtls does evil things to it:
        if not hasattr(self, "socket"):
            return
        abstract.FileDescriptor.connectionLost(self, reason)
        self._closeSocket(not reason.check(error.ConnectionAborted))
        protocol = self.protocol
        del self.protocol
        del self.socket
        del self.fileno
        protocol.connectionLost(reason)


    logstr = "Uninitialized"

    def logPrefix(self):
        """Return the prefix to log with when I own the logging thread.
        """
        return self.logstr

    def getTcpNoDelay(self):
        return operator.truth(self.socket.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY))

    def setTcpNoDelay(self, enabled):
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, enabled)

    def getTcpKeepAlive(self):
        return operator.truth(self.socket.getsockopt(socket.SOL_SOCKET,
                                                     socket.SO_KEEPALIVE))

    def setTcpKeepAlive(self, enabled):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, enabled)




class _BaseBaseClient(object):
    """
    Code shared with other (non-POSIX) reactors for management of general
    outgoing connections.

    Requirements upon subclasses are documented as instance variables rather
    than abstract methods, in order to avoid MRO confusion, since this base is
    mixed in to unfortunately weird and distinctive multiple-inheritance
    hierarchies and many of these attributes are provided by peer classes
    rather than descendant classes in those hierarchies.

    @ivar addressFamily: The address family constant (C{socket.AF_INET},
        C{socket.AF_INET6}, C{socket.AF_UNIX}) of the underlying socket of this
        client connection.
    @type addressFamily: C{int}

    @ivar socketType: The socket type constant (C{socket.SOCK_STREAM} or
        C{socket.SOCK_DGRAM}) of the underlying socket.
    @type socketType: C{int}

    @ivar _requiresResolution: A flag indicating whether the address of this
        client will require name resolution.  C{True} if the hostname of said
        address indicates a name that must be resolved by hostname lookup,
        C{False} if it indicates an IP address literal.
    @type _requiresResolution: C{bool}

    @cvar _commonConnection: Subclasses must provide this attribute, which
        indicates the L{Connection}-alike class to invoke C{__init__} and
        C{connectionLost} on.
    @type _commonConnection: C{type}

    @ivar _stopReadingAndWriting: Subclasses must implement in order to remove
        this transport from its reactor's notifications in response to a
        terminated connection attempt.
    @type _stopReadingAndWriting: 0-argument callable returning L{None}

    @ivar _closeSocket: Subclasses must implement in order to close the socket
        in response to a terminated connection attempt.
    @type _closeSocket: 1-argument callable; see L{_SocketCloser._closeSocket}

    @ivar _collectSocketDetails: Clean up references to the attached socket in
        its underlying OS resource (such as a file descriptor or file handle),
        as part of post connection-failure cleanup.
    @type _collectSocketDetails: 0-argument callable returning L{None}.

    @ivar reactor: The class pointed to by C{_commonConnection} should set this
        attribute in its constructor.
    @type reactor: L{twisted.internet.interfaces.IReactorTime},
        L{twisted.internet.interfaces.IReactorCore},
        L{twisted.internet.interfaces.IReactorFDSet}
    """

    addressFamily = socket.AF_INET
    socketType = socket.SOCK_STREAM

    def _finishInit(self, whenDone, skt, error, reactor):
        """
        Called by subclasses to continue to the stage of initialization where
        the socket connect attempt is made.

        @param whenDone: A 0-argument callable to invoke once the connection is
            set up.  This is L{None} if the connection could not be prepared
            due to a previous error.

        @param skt: The socket object to use to perform the connection.
        @type skt: C{socket._socketobject}

        @param error: The error to fail the connection with.

        @param reactor: The reactor to use for this client.
        @type reactor: L{twisted.internet.interfaces.IReactorTime}
        """
        if whenDone:
            self._commonConnection.__init__(self, skt, None, reactor)
            reactor.callLater(0, whenDone)
        else:
            reactor.callLater(0, self.failIfNotConnected, error)


    def resolveAddress(self):
        """
        Resolve the name that was passed to this L{_BaseBaseClient}, if
        necessary, and then move on to attempting the connection once an
        address has been determined.  (The connection will be attempted
        immediately within this function if either name resolution can be
        synchronous or the address was an IP address literal.)

        @note: You don't want to call this method from outside, as it won't do
            anything useful; it's just part of the connection bootstrapping
            process.  Also, although this method is on L{_BaseBaseClient} for
            historical reasons, it's not used anywhere except for L{Client}
            itself.

        @return: L{None}
        """
        if self._requiresResolution:
            d = self.reactor.resolve(self.addr[0])
            d.addCallback(lambda n: (n,) + self.addr[1:])
            d.addCallbacks(self._setRealAddress, self.failIfNotConnected)
        else:
            self._setRealAddress(self.addr)


    def _setRealAddress(self, address):
        """
        Set the resolved address of this L{_BaseBaseClient} and initiate the
        connection attempt.

        @param address: Depending on whether this is an IPv4 or IPv6 connection
            attempt, a 2-tuple of C{(host, port)} or a 4-tuple of C{(host,
            port, flow, scope)}.  At this point it is a fully resolved address,
            and the 'host' portion will always be an IP address, not a DNS
            name.
        """
        self.realAddress = address
        self.doConnect()


    def failIfNotConnected(self, err):
        """
        Generic method called when the attempts to connect failed. It basically
        cleans everything it can: call connectionFailed, stop read and write,
        delete socket related members.
        """
        if (self.connected or self.disconnected or
            not hasattr(self, "connector")):
            return

        self._stopReadingAndWriting()
        try:
            self._closeSocket(True)
        except AttributeError:
            pass
        else:
            self._collectSocketDetails()
        self.connector.connectionFailed(failure.Failure(err))
        del self.connector


    def stopConnecting(self):
        """
        If a connection attempt is still outstanding (i.e.  no connection is
        yet established), immediately stop attempting to connect.
        """
        self.failIfNotConnected(error.UserError())


    def connectionLost(self, reason):
        """
        Invoked by lower-level logic when it's time to clean the socket up.
        Depending on the state of the connection, either inform the attached
        L{Connector} that the connection attempt has failed, or inform the
        connected L{IProtocol} that the established connection has been lost.

        @param reason: the reason that the connection was terminated
        @type reason: L{Failure}
        """
        if not self.connected:
            self.failIfNotConnected(error.ConnectError(string=reason))
        else:
            self._commonConnection.connectionLost(self, reason)
            self.connector.connectionLost(reason)



class BaseClient(_BaseBaseClient, _TLSClientMixin, Connection):
    """
    A base class for client TCP (and similar) sockets.

    @ivar realAddress: The address object that will be used for socket.connect;
        this address is an address tuple (the number of elements dependent upon
        the address family) which does not contain any names which need to be
        resolved.
    @type realAddress: C{tuple}

    @ivar _base: L{Connection}, which is the base class of this class which has
        all of the useful file descriptor methods.  This is used by
        L{_TLSServerMixin} to call the right methods to directly manipulate the
        transport, as is necessary for writing TLS-encrypted bytes (whereas
        those methods on L{Server} will go through another layer of TLS if it
        has been enabled).
    """

    _base = Connection
    _commonConnection = Connection

    def _stopReadingAndWriting(self):
        """
        Implement the POSIX-ish (i.e.
        L{twisted.internet.interfaces.IReactorFDSet}) method of detaching this
        socket from the reactor for L{_BaseBaseClient}.
        """
        if hasattr(self, "reactor"):
            # this doesn't happen if we failed in __init__
            self.stopReading()
            self.stopWriting()


    def _collectSocketDetails(self):
        """
        Clean up references to the socket and its file descriptor.

        @see: L{_BaseBaseClient}
        """
        del self.socket, self.fileno


    def createInternetSocket(self):
        """(internal) Create a non-blocking socket using
        self.addressFamily, self.socketType.
        """
        s = socket.socket(self.addressFamily, self.socketType)
        s.setblocking(0)
        fdesc._setCloseOnExec(s.fileno())
        return s


    def doConnect(self):
        """
        Initiate the outgoing connection attempt.

        @note: Applications do not need to call this method; it will be invoked
            internally as part of L{IReactorTCP.connectTCP}.
        """
        self.doWrite = self.doConnect
        self.doRead = self.doConnect
        if not hasattr(self, "connector"):
            # this happens when connection failed but doConnect
            # was scheduled via a callLater in self._finishInit
            return

        err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err:
            self.failIfNotConnected(error.getConnectError((err, strerror(err))))
            return

        # doConnect gets called twice.  The first time we actually need to
        # start the connection attempt.  The second time we don't really
        # want to (SO_ERROR above will have taken care of any errors, and if
        # it reported none, the mere fact that doConnect was called again is
        # sufficient to indicate that the connection has succeeded), but it
        # is not /particularly/ detrimental to do so.  This should get
        # cleaned up some day, though.
        try:
            connectResult = self.socket.connect_ex(self.realAddress)
        except socket.error as se:
            connectResult = se.args[0]
        if connectResult:
            if connectResult == EISCONN:
                pass
            # on Windows EINVAL means sometimes that we should keep trying:
            # http://msdn.microsoft.com/library/default.asp?url=/library/en-us/winsock/winsock/connect_2.asp
            elif ((connectResult in (EWOULDBLOCK, EINPROGRESS, EALREADY)) or
                  (connectResult == EINVAL and platformType == "win32")):
                self.startReading()
                self.startWriting()
                return
            else:
                self.failIfNotConnected(error.getConnectError((connectResult, strerror(connectResult))))
                return

        # If I have reached this point without raising or returning, that means
        # that the socket is connected.
        del self.doWrite
        del self.doRead
        # we first stop and then start, to reset any references to the old doRead
        self.stopReading()
        self.stopWriting()
        self._connectDone()


    def _connectDone(self):
        """
        This is a hook for when a connection attempt has succeeded.

        Here, we build the protocol from the
        L{twisted.internet.protocol.ClientFactory} that was passed in, compute
        a log string, begin reading so as to send traffic to the newly built
        protocol, and finally hook up the protocol itself.

        This hook is overridden by L{ssl.Client} to initiate the TLS protocol.
        """
        self.protocol = self.connector.buildProtocol(self.getPeer())
        self.connected = 1
        logPrefix = self._getLogPrefix(self.protocol)
        self.logstr = "%s,client" % logPrefix
        if self.protocol is None:
            # Factory.buildProtocol is allowed to return None.  In that case,
            # make up a protocol to satisfy the rest of the implementation;
            # connectionLost is going to be called on something, for example.
            # This is easier than adding special case support for a None
            # protocol throughout the rest of the transport implementation.
            self.protocol = Protocol()
            # But dispose of the connection quickly.
            self.loseConnection()
        else:
            self.startReading()
            self.protocol.makeConnection(self)



_NUMERIC_ONLY = socket.AI_NUMERICHOST | _AI_NUMERICSERV

def _resolveIPv6(ip, port):
    """
    Resolve an IPv6 literal into an IPv6 address.

    This is necessary to resolve any embedded scope identifiers to the relevant
    C{sin6_scope_id} for use with C{socket.connect()}, C{socket.listen()}, or
    C{socket.bind()}; see U{RFC 3493 <https://tools.ietf.org/html/rfc3493>} for
    more information.

    @param ip: An IPv6 address literal.
    @type ip: C{str}

    @param port: A port number.
    @type port: C{int}

    @return: a 4-tuple of C{(host, port, flow, scope)}, suitable for use as an
        IPv6 address.

    @raise socket.gaierror: if either the IP or port is not numeric as it
        should be.
    """
    return socket.getaddrinfo(ip, port, 0, 0, 0, _NUMERIC_ONLY)[0][4]



class _BaseTCPClient(object):
    """
    Code shared with other (non-POSIX) reactors for management of outgoing TCP
    connections (both TCPv4 and TCPv6).

    @note: In order to be functional, this class must be mixed into the same
        hierarchy as L{_BaseBaseClient}.  It would subclass L{_BaseBaseClient}
        directly, but the class hierarchy here is divided in strange ways out
        of the need to share code along multiple axes; specifically, with the
        IOCP reactor and also with UNIX clients in other reactors.

    @ivar _addressType: The Twisted _IPAddress implementation for this client
    @type _addressType: L{IPv4Address} or L{IPv6Address}

    @ivar connector: The L{Connector} which is driving this L{_BaseTCPClient}'s
        connection attempt.

    @ivar addr: The address that this socket will be connecting to.
    @type addr: If IPv4, a 2-C{tuple} of C{(str host, int port)}.  If IPv6, a
        4-C{tuple} of (C{str host, int port, int ignored, int scope}).

    @ivar createInternetSocket: Subclasses must implement this as a method to
        create a python socket object of the appropriate address family and
        socket type.
    @type createInternetSocket: 0-argument callable returning
        C{socket._socketobject}.
    """

    _addressType = address.IPv4Address

    def __init__(self, host, port, bindAddress, connector, reactor=None):
        # BaseClient.__init__ is invoked later
        self.connector = connector
        self.addr = (host, port)

        whenDone = self.resolveAddress
        err = None
        skt = None

        if abstract.isIPAddress(host):
            self._requiresResolution = False
        elif abstract.isIPv6Address(host):
            self._requiresResolution = False
            self.addr = _resolveIPv6(host, port)
            self.addressFamily = socket.AF_INET6
            self._addressType = address.IPv6Address
        else:
            self._requiresResolution = True
        try:
            skt = self.createInternetSocket()
        except socket.error as se:
            err = error.ConnectBindError(se.args[0], se.args[1])
            whenDone = None
        if whenDone and bindAddress is not None:
            try:
                if abstract.isIPv6Address(bindAddress[0]):
                    bindinfo = _resolveIPv6(*bindAddress)
                else:
                    bindinfo = bindAddress
                skt.bind(bindinfo)
            except socket.error as se:
                err = error.ConnectBindError(se.args[0], se.args[1])
                whenDone = None
        self._finishInit(whenDone, skt, err, reactor)


    def getHost(self):
        """
        Returns an L{IPv4Address} or L{IPv6Address}.

        This indicates the address from which I am connecting.
        """
        return self._addressType('TCP', *self.socket.getsockname()[:2])


    def getPeer(self):
        """
        Returns an L{IPv4Address} or L{IPv6Address}.

        This indicates the address that I am connected to.
        """
        # an ipv6 realAddress has more than two elements, but the IPv6Address
        # constructor still only takes two.
        return self._addressType('TCP', *self.realAddress[:2])


    def __repr__(self):
        s = '<%s to %s at %x>' % (self.__class__, self.addr, id(self))
        return s



class Client(_BaseTCPClient, BaseClient):
    """
    A transport for a TCP protocol; either TCPv4 or TCPv6.

    Do not create these directly; use L{IReactorTCP.connectTCP}.
    """



class Server(_TLSServerMixin, Connection):
    """
    Serverside socket-stream connection class.

    This is a serverside network connection transport; a socket which came from
    an accept() on a server.

    @ivar _base: L{Connection}, which is the base class of this class which has
        all of the useful file descriptor methods.  This is used by
        L{_TLSServerMixin} to call the right methods to directly manipulate the
        transport, as is necessary for writing TLS-encrypted bytes (whereas
        those methods on L{Server} will go through another layer of TLS if it
        has been enabled).
    """
    _base = Connection

    _addressType = address.IPv4Address

    def __init__(self, sock, protocol, client, server, sessionno, reactor):
        """
        Server(sock, protocol, client, server, sessionno)

        Initialize it with a socket, a protocol, a descriptor for my peer (a
        tuple of host, port describing the other end of the connection), an
        instance of Port, and a session number.
        """
        Connection.__init__(self, sock, protocol, reactor)
        if len(client) != 2:
            self._addressType = address.IPv6Address
        self.server = server
        self.client = client
        self.sessionno = sessionno
        self.hostname = client[0]

        logPrefix = self._getLogPrefix(self.protocol)
        self.logstr = "%s,%s,%s" % (logPrefix,
                                    sessionno,
                                    self.hostname)
        if self.server is not None:
            self.repstr = "<%s #%s on %s>" % (self.protocol.__class__.__name__,
                                              self.sessionno,
                                              self.server._realPortNumber)
        self.startReading()
        self.connected = 1

    def __repr__(self):
        """
        A string representation of this connection.
        """
        return self.repstr


    @classmethod
    def _fromConnectedSocket(cls, fileDescriptor, addressFamily, factory,
                             reactor):
        """
        Create a new L{Server} based on an existing connected I{SOCK_STREAM}
        socket.

        Arguments are the same as to L{Server.__init__}, except where noted.

        @param fileDescriptor: An integer file descriptor associated with a
            connected socket.  The socket must be in non-blocking mode.  Any
            additional attributes desired, such as I{FD_CLOEXEC}, must also be
            set already.

        @param addressFamily: The address family (sometimes called I{domain})
            of the existing socket.  For example, L{socket.AF_INET}.

        @return: A new instance of C{cls} wrapping the socket given by
            C{fileDescriptor}.
        """
        addressType = address.IPv4Address
        if addressFamily == socket.AF_INET6:
            addressType = address.IPv6Address
        skt = socket.fromfd(fileDescriptor, addressFamily, socket.SOCK_STREAM)
        addr = skt.getpeername()
        protocolAddr = addressType('TCP', addr[0], addr[1])
        localPort = skt.getsockname()[1]

        protocol = factory.buildProtocol(protocolAddr)
        if protocol is None:
            skt.close()
            return

        self = cls(skt, protocol, addr, None, addr[1], reactor)
        self.repstr = "<%s #%s on %s>" % (
            self.protocol.__class__.__name__, self.sessionno, localPort)
        protocol.makeConnection(self)
        return self


    def getHost(self):
        """
        Returns an L{IPv4Address} or L{IPv6Address}.

        This indicates the server's address.
        """
        host, port = self.socket.getsockname()[:2]
        return self._addressType('TCP', host, port)


    def getPeer(self):
        """
        Returns an L{IPv4Address} or L{IPv6Address}.

        This indicates the client's address.
        """
        return self._addressType('TCP', *self.client[:2])



@implementer(interfaces.IListeningPort)
class Port(base.BasePort, _SocketCloser):
    """
    A TCP server port, listening for connections.

    When a connection is accepted, this will call a factory's buildProtocol
    with the incoming address as an argument, according to the specification
    described in L{twisted.internet.interfaces.IProtocolFactory}.

    If you wish to change the sort of transport that will be used, the
    C{transport} attribute will be called with the signature expected for
    C{Server.__init__}, so it can be replaced.

    @ivar deferred: a deferred created when L{stopListening} is called, and
        that will fire when connection is lost. This is not to be used it
        directly: prefer the deferred returned by L{stopListening} instead.
    @type deferred: L{defer.Deferred}

    @ivar disconnecting: flag indicating that the L{stopListening} method has
        been called and that no connections should be accepted anymore.
    @type disconnecting: C{bool}

    @ivar connected: flag set once the listen has successfully been called on
        the socket.
    @type connected: C{bool}

    @ivar _type: A string describing the connections which will be created by
        this port.  Normally this is C{"TCP"}, since this is a TCP port, but
        when the TLS implementation re-uses this class it overrides the value
        with C{"TLS"}.  Only used for logging.

    @ivar _preexistingSocket: If not L{None}, a L{socket.socket} instance which
        was created and initialized outside of the reactor and will be used to
        listen for connections (instead of a new socket being created by this
        L{Port}).
    """

    socketType = socket.SOCK_STREAM

    transport = Server
    sessionno = 0
    interface = ''
    backlog = 50

    _type = 'TCP'

    # Actual port number being listened on, only set to a non-None
    # value when we are actually listening.
    _realPortNumber = None

    # An externally initialized socket that we will use, rather than creating
    # our own.
    _preexistingSocket = None

    addressFamily = socket.AF_INET
    _addressType = address.IPv4Address

    def __init__(self, port, factory, backlog=50, interface='', reactor=None):
        """Initialize with a numeric port to listen on.
        """
        base.BasePort.__init__(self, reactor=reactor)
        self.port = port
        self.factory = factory
        self.backlog = backlog
        if abstract.isIPv6Address(interface):
            self.addressFamily = socket.AF_INET6
            self._addressType = address.IPv6Address
        self.interface = interface


    @classmethod
    def _fromListeningDescriptor(cls, reactor, fd, addressFamily, factory):
        """
        Create a new L{Port} based on an existing listening I{SOCK_STREAM}
        socket.

        Arguments are the same as to L{Port.__init__}, except where noted.

        @param fd: An integer file descriptor associated with a listening
            socket.  The socket must be in non-blocking mode.  Any additional
            attributes desired, such as I{FD_CLOEXEC}, must also be set already.

        @param addressFamily: The address family (sometimes called I{domain}) of
            the existing socket.  For example, L{socket.AF_INET}.

        @return: A new instance of C{cls} wrapping the socket given by C{fd}.
        """
        port = socket.fromfd(fd, addressFamily, cls.socketType)
        interface = port.getsockname()[0]
        self = cls(None, factory, None, interface, reactor)
        self._preexistingSocket = port
        return self


    def __repr__(self):
        if self._realPortNumber is not None:
            return "<%s of %s on %s>" % (self.__class__,
                self.factory.__class__, self._realPortNumber)
        else:
            return "<%s of %s (not listening)>" % (self.__class__, self.factory.__class__)

    def createInternetSocket(self):
        s = base.BasePort.createInternetSocket(self)
        if platformType == "posix" and sys.platform != "cygwin":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s


    def startListening(self):
        """Create and bind my socket, and begin listening on it.

        This is called on unserialization, and must be called after creating a
        server to begin listening on the specified port.
        """
        if self._preexistingSocket is None:
            # Create a new socket and make it listen
            try:
                skt = self.createInternetSocket()
                if self.addressFamily == socket.AF_INET6:
                    addr = _resolveIPv6(self.interface, self.port)
                else:
                    addr = (self.interface, self.port)
                skt.bind(addr)
            except socket.error as le:
                raise CannotListenError(self.interface, self.port, le)
            skt.listen(self.backlog)
        else:
            # Re-use the externally specified socket
            skt = self._preexistingSocket
            self._preexistingSocket = None
            # Avoid shutting it down at the end.
            self._shouldShutdown = False

        # Make sure that if we listened on port 0, we update that to
        # reflect what the OS actually assigned us.
        self._realPortNumber = skt.getsockname()[1]

        log.msg("%s starting on %s" % (
                self._getLogPrefix(self.factory), self._realPortNumber))

        # The order of the next 5 lines is kind of bizarre.  If no one
        # can explain it, perhaps we should re-arrange them.
        self.factory.doStart()
        self.connected = True
        self.socket = skt
        self.fileno = self.socket.fileno
        self.numberAccepts = 100

        self.startReading()


    def _buildAddr(self, address):
        host, port = address[:2]
        return self._addressType('TCP', host, port)


    def doRead(self):
        """Called when my socket is ready for reading.

        This accepts a connection and calls self.protocol() to handle the
        wire-level protocol.
        """
        try:
            if platformType == "posix":
                numAccepts = self.numberAccepts
            else:
                # win32 event loop breaks if we do more than one accept()
                # in an iteration of the event loop.
                numAccepts = 1
            for i in range(numAccepts):
                # we need this so we can deal with a factory's buildProtocol
                # calling our loseConnection
                if self.disconnecting:
                    return
                try:
                    skt, addr = self.socket.accept()
                except socket.error as e:
                    if e.args[0] in (EWOULDBLOCK, EAGAIN):
                        self.numberAccepts = i
                        break
                    elif e.args[0] == EPERM:
                        # Netfilter on Linux may have rejected the
                        # connection, but we get told to try to accept()
                        # anyway.
                        continue
                    elif e.args[0] in (EMFILE, ENOBUFS, ENFILE, ENOMEM, ECONNABORTED):

                        # Linux gives EMFILE when a process is not allowed
                        # to allocate any more file descriptors.  *BSD and
                        # Win32 give (WSA)ENOBUFS.  Linux can also give
                        # ENFILE if the system is out of inodes, or ENOMEM
                        # if there is insufficient memory to allocate a new
                        # dentry.  ECONNABORTED is documented as possible on
                        # both Linux and Windows, but it is not clear
                        # whether there are actually any circumstances under
                        # which it can happen (one might expect it to be
                        # possible if a client sends a FIN or RST after the
                        # server sends a SYN|ACK but before application code
                        # calls accept(2), however at least on Linux this
                        # _seems_ to be short-circuited by syncookies.

                        log.msg("Could not accept new connection (%s)" % (
                            errorcode[e.args[0]],))
                        break
                    raise

                fdesc._setCloseOnExec(skt.fileno())
                protocol = self.factory.buildProtocol(self._buildAddr(addr))
                if protocol is None:
                    skt.close()
                    continue
                s = self.sessionno
                self.sessionno = s+1
                transport = self.transport(skt, protocol, addr, self, s, self.reactor)
                protocol.makeConnection(transport)
            else:
                self.numberAccepts = self.numberAccepts+20
        except:
            # Note that in TLS mode, this will possibly catch SSL.Errors
            # raised by self.socket.accept()
            #
            # There is no "except SSL.Error:" above because SSL may be
            # None if there is no SSL support.  In any case, all the
            # "except SSL.Error:" suite would probably do is log.deferr()
            # and return, so handling it here works just as well.
            log.deferr()

    def loseConnection(self, connDone=failure.Failure(main.CONNECTION_DONE)):
        """
        Stop accepting connections on this port.

        This will shut down the socket and call self.connectionLost().  It
        returns a deferred which will fire successfully when the port is
        actually closed, or with a failure if an error occurs shutting down.
        """
        self.disconnecting = True
        self.stopReading()
        if self.connected:
            self.deferred = deferLater(
                self.reactor, 0, self.connectionLost, connDone)
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

        base.BasePort.connectionLost(self, reason)
        self.connected = False
        self._closeSocket(True)
        del self.socket
        del self.fileno

        try:
            self.factory.doStop()
        finally:
            self.disconnecting = False


    def logPrefix(self):
        """Returns the name of my class, to prefix log entries with.
        """
        return reflect.qual(self.factory.__class__)


    def getHost(self):
        """
        Return an L{IPv4Address} or L{IPv6Address} indicating the listening
        address of this port.
        """
        host, port = self.socket.getsockname()[:2]
        return self._addressType('TCP', host, port)



class Connector(base.BaseConnector):
    """
    A L{Connector} provides of L{twisted.internet.interfaces.IConnector} for
    all POSIX-style reactors.

    @ivar _addressType: the type returned by L{Connector.getDestination}.
        Either L{IPv4Address} or L{IPv6Address}, depending on the type of
        address.
    @type _addressType: C{type}
    """
    _addressType = address.IPv4Address

    def __init__(self, host, port, factory, timeout, bindAddress, reactor=None):
        if isinstance(port, _portNameType):
            try:
                port = socket.getservbyname(port, 'tcp')
            except socket.error as e:
                raise error.ServiceNameUnknownError(string="%s (%r)" % (e, port))
        self.host, self.port = host, port
        if abstract.isIPv6Address(host):
            self._addressType = address.IPv6Address
        self.bindAddress = bindAddress
        base.BaseConnector.__init__(self, factory, timeout, reactor)


    def _makeTransport(self):
        """
        Create a L{Client} bound to this L{Connector}.

        @return: a new L{Client}
        @rtype: L{Client}
        """
        return Client(self.host, self.port, self.bindAddress, self, self.reactor)


    def getDestination(self):
        """
        @see: L{twisted.internet.interfaces.IConnector.getDestination}.
        """
        return self._addressType('TCP', self.host, self.port)
