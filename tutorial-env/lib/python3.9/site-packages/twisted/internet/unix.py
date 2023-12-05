# -*- test-case-name: twisted.test.test_unix,twisted.internet.test.test_unix,twisted.internet.test.test_posixbase -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
UNIX socket support for Twisted.

End users shouldn't use this module directly - use the reactor APIs instead.

Maintainer: Itamar Shtull-Trauring
"""


import os
import socket
import stat
import struct
from errno import EAGAIN, ECONNREFUSED, EINTR, EMSGSIZE, ENOBUFS, EWOULDBLOCK
from typing import Optional, Type

from zope.interface import implementedBy, implementer, implementer_only

from twisted.internet import address, base, error, interfaces, main, protocol, tcp, udp
from twisted.internet.abstract import FileDescriptor
from twisted.python import failure, lockfile, log, reflect
from twisted.python.compat import lazyByteSlice
from twisted.python.filepath import _coerceToFilesystemEncoding
from twisted.python.util import untilConcludes

try:
    from twisted.python import sendmsg as _sendmsg
except ImportError:
    sendmsg = None
else:
    sendmsg = _sendmsg

if not hasattr(socket, "AF_UNIX"):
    raise ImportError("UNIX sockets not supported on this platform")


def _ancillaryDescriptor(fd):
    """
    Pack an integer into an ancillary data structure suitable for use with
    L{sendmsg.sendmsg}.
    """
    packed = struct.pack("i", fd)
    return [(socket.SOL_SOCKET, sendmsg.SCM_RIGHTS, packed)]


class _SendmsgMixin:
    """
    Mixin for stream-oriented UNIX transports which uses sendmsg and recvmsg to
    offer additional functionality, such as copying file descriptors into other
    processes.

    @ivar _writeSomeDataBase: The class which provides the basic implementation
        of C{writeSomeData}.  Ultimately this should be a subclass of
        L{twisted.internet.abstract.FileDescriptor}.  Subclasses which mix in
        L{_SendmsgMixin} must define this.

    @ivar _sendmsgQueue: A C{list} of C{int} holding file descriptors which are
        currently buffered before being sent.

    @ivar _fileDescriptorBufferSize: An C{int} giving the maximum number of file
        descriptors to accept and queue for sending before pausing the
        registered producer, if there is one.
    """

    _writeSomeDataBase: Optional[Type[FileDescriptor]] = None
    _fileDescriptorBufferSize = 64

    def __init__(self):
        self._sendmsgQueue = []

    def _isSendBufferFull(self):
        """
        Determine whether the user-space send buffer for this transport is full
        or not.

        This extends the base determination by adding consideration of how many
        file descriptors need to be sent using L{sendmsg.sendmsg}.  When there
        are more than C{self._fileDescriptorBufferSize}, the buffer is
        considered full.

        @return: C{True} if it is full, C{False} otherwise.
        """
        # There must be some bytes in the normal send buffer, checked by
        # _writeSomeDataBase._isSendBufferFull, in order to send file
        # descriptors from _sendmsgQueue.  That means that the buffer will
        # eventually be considered full even without this additional logic.
        # However, since we send only one byte per file descriptor, having lots
        # of elements in _sendmsgQueue incurs more overhead and perhaps slows
        # things down.  Anyway, try this for now, maybe rethink it later.
        return len(
            self._sendmsgQueue
        ) > self._fileDescriptorBufferSize or self._writeSomeDataBase._isSendBufferFull(
            self
        )

    def sendFileDescriptor(self, fileno):
        """
        Queue the given file descriptor to be sent and start trying to send it.
        """
        self._sendmsgQueue.append(fileno)
        self._maybePauseProducer()
        self.startWriting()

    def writeSomeData(self, data):
        """
        Send as much of C{data} as possible.  Also send any pending file
        descriptors.
        """
        # Make it a programming error to send more file descriptors than you
        # send regular bytes.  Otherwise, due to the limitation mentioned
        # below, we could end up with file descriptors left, but no bytes to
        # send with them, therefore no way to send those file descriptors.
        if len(self._sendmsgQueue) > len(data):
            return error.FileDescriptorOverrun()

        # If there are file descriptors to send, try sending them first, using
        # a little bit of data from the stream-oriented write buffer too.  It
        # is not possible to send a file descriptor without sending some
        # regular data.
        index = 0
        try:
            while index < len(self._sendmsgQueue):
                fd = self._sendmsgQueue[index]
                try:
                    untilConcludes(
                        sendmsg.sendmsg,
                        self.socket,
                        data[index : index + 1],
                        _ancillaryDescriptor(fd),
                    )
                except OSError as se:
                    if se.args[0] in (EWOULDBLOCK, ENOBUFS):
                        return index
                    else:
                        return main.CONNECTION_LOST
                else:
                    index += 1
        finally:
            del self._sendmsgQueue[:index]

        # Hand the remaining data to the base implementation.  Avoid slicing in
        # favor of a buffer, in case that happens to be any faster.
        limitedData = lazyByteSlice(data, index)
        result = self._writeSomeDataBase.writeSomeData(self, limitedData)
        try:
            return index + result
        except TypeError:
            return result

    def doRead(self):
        """
        Calls {IProtocol.dataReceived} with all available data and
        L{IFileDescriptorReceiver.fileDescriptorReceived} once for each
        received file descriptor in ancillary data.

        This reads up to C{self.bufferSize} bytes of data from its socket, then
        dispatches the data to protocol callbacks to be handled.  If the
        connection is not lost through an error in the underlying recvmsg(),
        this function will return the result of the dataReceived call.
        """
        try:
            data, ancillary, flags = untilConcludes(
                sendmsg.recvmsg, self.socket, self.bufferSize
            )
        except OSError as se:
            if se.args[0] == EWOULDBLOCK:
                return
            else:
                return main.CONNECTION_LOST

        for cmsgLevel, cmsgType, cmsgData in ancillary:
            if cmsgLevel == socket.SOL_SOCKET and cmsgType == sendmsg.SCM_RIGHTS:
                self._ancillaryLevelSOLSOCKETTypeSCMRIGHTS(cmsgData)
            else:
                log.msg(
                    format=(
                        "%(protocolName)s (on %(hostAddress)r) "
                        "received unsupported ancillary data "
                        "(level=%(cmsgLevel)r, type=%(cmsgType)r) "
                        "from %(peerAddress)r."
                    ),
                    hostAddress=self.getHost(),
                    peerAddress=self.getPeer(),
                    protocolName=self._getLogPrefix(self.protocol),
                    cmsgLevel=cmsgLevel,
                    cmsgType=cmsgType,
                )

        return self._dataReceived(data)

    def _ancillaryLevelSOLSOCKETTypeSCMRIGHTS(self, cmsgData):
        """
        Processes ancillary data with level SOL_SOCKET and type SCM_RIGHTS,
        indicating that the ancillary data payload holds file descriptors.

        Calls L{IFileDescriptorReceiver.fileDescriptorReceived} once for each
        received file descriptor or logs a message if the protocol does not
        implement L{IFileDescriptorReceiver}.

        @param cmsgData: Ancillary data payload.
        @type cmsgData: L{bytes}
        """

        fdCount = len(cmsgData) // 4
        fds = struct.unpack("i" * fdCount, cmsgData)
        if interfaces.IFileDescriptorReceiver.providedBy(self.protocol):
            for fd in fds:
                self.protocol.fileDescriptorReceived(fd)
        else:
            log.msg(
                format=(
                    "%(protocolName)s (on %(hostAddress)r) does not "
                    "provide IFileDescriptorReceiver; closing file "
                    "descriptor received (from %(peerAddress)r)."
                ),
                hostAddress=self.getHost(),
                peerAddress=self.getPeer(),
                protocolName=self._getLogPrefix(self.protocol),
            )
            for fd in fds:
                os.close(fd)


class _UnsupportedSendmsgMixin:
    """
    Behaviorless placeholder used when C{twisted.python.sendmsg} is not
    available, preventing L{IUNIXTransport} from being supported.
    """


if sendmsg:
    _SendmsgMixin = _SendmsgMixin
else:
    _SendmsgMixin = _UnsupportedSendmsgMixin  # type: ignore[assignment,misc]


@implementer(interfaces.IUNIXTransport)
class Server(_SendmsgMixin, tcp.Server):

    _writeSomeDataBase = tcp.Server

    def __init__(self, sock, protocol, client, server, sessionno, reactor):
        _SendmsgMixin.__init__(self)
        tcp.Server.__init__(
            self, sock, protocol, (client, None), server, sessionno, reactor
        )

    @classmethod
    def _fromConnectedSocket(cls, fileDescriptor, factory, reactor):
        """
        Create a new L{Server} based on an existing connected I{SOCK_STREAM}
        socket.

        Arguments are the same as to L{Server.__init__}, except where noted.

        @param fileDescriptor: An integer file descriptor associated with a
            connected socket.  The socket must be in non-blocking mode.  Any
            additional attributes desired, such as I{FD_CLOEXEC}, must also be
            set already.

        @return: A new instance of C{cls} wrapping the socket given by
            C{fileDescriptor}.
        """
        skt = socket.fromfd(fileDescriptor, socket.AF_UNIX, socket.SOCK_STREAM)
        protocolAddr = address.UNIXAddress(skt.getsockname())

        proto = factory.buildProtocol(protocolAddr)
        if proto is None:
            skt.close()
            return

        # FIXME: is this a suitable sessionno?
        sessionno = 0
        self = cls(skt, proto, skt.getpeername(), None, sessionno, reactor)
        self.repstr = "<{} #{} on {}>".format(
            self.protocol.__class__.__name__,
            self.sessionno,
            skt.getsockname(),
        )
        self.logstr = "{},{},{}".format(
            self.protocol.__class__.__name__,
            self.sessionno,
            skt.getsockname(),
        )
        proto.makeConnection(self)
        return self

    def getHost(self):
        return address.UNIXAddress(self.socket.getsockname())

    def getPeer(self):
        return address.UNIXAddress(self.hostname or None)


def _inFilesystemNamespace(path):
    """
    Determine whether the given unix socket path is in a filesystem namespace.

    While most PF_UNIX sockets are entries in the filesystem, Linux 2.2 and
    above support PF_UNIX sockets in an "abstract namespace" that does not
    correspond to any path. This function returns C{True} if the given socket
    path is stored in the filesystem and C{False} if the path is in this
    abstract namespace.
    """
    return path[:1] not in (b"\0", "\0")


class _UNIXPort:
    def getHost(self):
        """
        Returns a UNIXAddress.

        This indicates the server's address.
        """
        return address.UNIXAddress(self.socket.getsockname())


class Port(_UNIXPort, tcp.Port):
    addressFamily = socket.AF_UNIX
    socketType = socket.SOCK_STREAM

    transport = Server
    lockFile = None

    def __init__(
        self, fileName, factory, backlog=50, mode=0o666, reactor=None, wantPID=0
    ):
        tcp.Port.__init__(
            self, self._buildAddr(fileName).name, factory, backlog, reactor=reactor
        )
        self.mode = mode
        self.wantPID = wantPID
        self._preexistingSocket = None

    @classmethod
    def _fromListeningDescriptor(cls, reactor, fd, factory):
        """
        Create a new L{Port} based on an existing listening I{SOCK_STREAM}
        socket.

        Arguments are the same as to L{Port.__init__}, except where noted.

        @param fd: An integer file descriptor associated with a listening
            socket.  The socket must be in non-blocking mode.  Any additional
            attributes desired, such as I{FD_CLOEXEC}, must also be set already.

        @return: A new instance of C{cls} wrapping the socket given by C{fd}.
        """
        port = socket.fromfd(fd, cls.addressFamily, cls.socketType)
        self = cls(port.getsockname(), factory, reactor=reactor)
        self._preexistingSocket = port
        return self

    def __repr__(self) -> str:
        factoryName = reflect.qual(self.factory.__class__)
        if hasattr(self, "socket"):
            return "<{} on {!r}>".format(
                factoryName,
                _coerceToFilesystemEncoding("", self.port),
            )
        else:
            return f"<{factoryName} (not listening)>"

    def _buildAddr(self, name):
        return address.UNIXAddress(name)

    def startListening(self):
        """
        Create and bind my socket, and begin listening on it.

        This is called on unserialization, and must be called after creating a
        server to begin listening on the specified port.
        """
        tcp._reservedFD.reserve()
        log.msg(
            "%s starting on %r"
            % (
                self._getLogPrefix(self.factory),
                _coerceToFilesystemEncoding("", self.port),
            )
        )
        if self.wantPID:
            self.lockFile = lockfile.FilesystemLock(self.port + b".lock")
            if not self.lockFile.lock():
                raise error.CannotListenError(None, self.port, "Cannot acquire lock")
            else:
                if not self.lockFile.clean:
                    try:
                        # This is a best-attempt at cleaning up
                        # left-over unix sockets on the filesystem.
                        # If it fails, there's not much else we can
                        # do.  The bind() below will fail with an
                        # exception that actually propagates.
                        if stat.S_ISSOCK(os.stat(self.port).st_mode):
                            os.remove(self.port)
                    except BaseException:
                        pass

        self.factory.doStart()

        try:
            if self._preexistingSocket is not None:
                skt = self._preexistingSocket
                self._preexistingSocket = None
            else:
                skt = self.createInternetSocket()
                skt.bind(self.port)
        except OSError as le:
            raise error.CannotListenError(None, self.port, le)
        else:
            if _inFilesystemNamespace(self.port):
                # Make the socket readable and writable to the world.
                os.chmod(self.port, self.mode)
            skt.listen(self.backlog)
            self.connected = True
            self.socket = skt
            self.fileno = self.socket.fileno
            self.numberAccepts = 100
            self.startReading()

    def _logConnectionLostMsg(self):
        """
        Log message for closing socket
        """
        log.msg(
            "(UNIX Port %s Closed)"
            % (
                _coerceToFilesystemEncoding(
                    "",
                    self.port,
                )
            )
        )

    def connectionLost(self, reason):
        if _inFilesystemNamespace(self.port):
            os.unlink(self.port)
        if self.lockFile is not None:
            self.lockFile.unlock()
        tcp.Port.connectionLost(self, reason)


@implementer(interfaces.IUNIXTransport)
class Client(_SendmsgMixin, tcp.BaseClient):
    """A client for Unix sockets."""

    addressFamily = socket.AF_UNIX
    socketType = socket.SOCK_STREAM
    _writeSomeDataBase = tcp.BaseClient

    def __init__(self, filename, connector, reactor=None, checkPID=0):
        _SendmsgMixin.__init__(self)
        # Normalise the filename using UNIXAddress
        filename = address.UNIXAddress(filename).name
        self.connector = connector
        self.realAddress = self.addr = filename
        if checkPID and not lockfile.isLocked(filename + b".lock"):
            self._finishInit(None, None, error.BadFileError(filename), reactor)
        self._finishInit(self.doConnect, self.createInternetSocket(), None, reactor)

    def getPeer(self):
        return address.UNIXAddress(self.addr)

    def getHost(self):
        return address.UNIXAddress(None)


class Connector(base.BaseConnector):
    def __init__(self, address, factory, timeout, reactor, checkPID):
        base.BaseConnector.__init__(self, factory, timeout, reactor)
        self.address = address
        self.checkPID = checkPID

    def _makeTransport(self):
        return Client(self.address, self, self.reactor, self.checkPID)

    def getDestination(self):
        return address.UNIXAddress(self.address)


@implementer(interfaces.IUNIXDatagramTransport)
class DatagramPort(_UNIXPort, udp.Port):
    """
    Datagram UNIX port, listening for packets.
    """

    addressFamily = socket.AF_UNIX

    def __init__(self, addr, proto, maxPacketSize=8192, mode=0o666, reactor=None):
        """Initialize with address to listen on."""
        udp.Port.__init__(
            self, addr, proto, maxPacketSize=maxPacketSize, reactor=reactor
        )
        self.mode = mode

    def __repr__(self) -> str:
        protocolName = reflect.qual(
            self.protocol.__class__,
        )
        if hasattr(self, "socket"):
            return f"<{protocolName} on {self.port!r}>"
        else:
            return f"<{protocolName} (not listening)>"

    def _bindSocket(self):
        log.msg(f"{self.protocol.__class__} starting on {repr(self.port)}")
        try:
            skt = self.createInternetSocket()  # XXX: haha misnamed method
            if self.port:
                skt.bind(self.port)
        except OSError as le:
            raise error.CannotListenError(None, self.port, le)
        if self.port and _inFilesystemNamespace(self.port):
            # Make the socket readable and writable to the world.
            os.chmod(self.port, self.mode)
        self.connected = 1
        self.socket = skt
        self.fileno = self.socket.fileno

    def write(self, datagram, address):
        """Write a datagram."""
        try:
            return self.socket.sendto(datagram, address)
        except OSError as se:
            no = se.args[0]
            if no == EINTR:
                return self.write(datagram, address)
            elif no == EMSGSIZE:
                raise error.MessageLengthError("message too long")
            elif no == EAGAIN:
                # oh, well, drop the data. The only difference from UDP
                # is that UDP won't ever notice.
                # TODO: add TCP-like buffering
                pass
            else:
                raise

    def connectionLost(self, reason=None):
        """Cleans up my socket."""
        log.msg("(Port %s Closed)" % repr(self.port))
        base.BasePort.connectionLost(self, reason)
        if hasattr(self, "protocol"):
            # we won't have attribute in ConnectedPort, in cases
            # where there was an error in connection process
            self.protocol.doStop()
        self.connected = 0
        self.socket.close()
        del self.socket
        del self.fileno
        if hasattr(self, "d"):
            self.d.callback(None)
            del self.d

    def setLogStr(self):
        self.logstr = reflect.qual(self.protocol.__class__) + " (UDP)"


@implementer_only(
    interfaces.IUNIXDatagramConnectedTransport, *(implementedBy(base.BasePort))
)
class ConnectedDatagramPort(DatagramPort):
    """
    A connected datagram UNIX socket.
    """

    def __init__(
        self,
        addr,
        proto,
        maxPacketSize=8192,
        mode=0o666,
        bindAddress=None,
        reactor=None,
    ):
        assert isinstance(proto, protocol.ConnectedDatagramProtocol)
        DatagramPort.__init__(self, bindAddress, proto, maxPacketSize, mode, reactor)
        self.remoteaddr = addr

    def startListening(self):
        try:
            self._bindSocket()
            self.socket.connect(self.remoteaddr)
            self._connectToProtocol()
        except BaseException:
            self.connectionFailed(failure.Failure())

    def connectionFailed(self, reason):
        """
        Called when a connection fails. Stop listening on the socket.

        @type reason: L{Failure}
        @param reason: Why the connection failed.
        """
        self.stopListening()
        self.protocol.connectionFailed(reason)
        del self.protocol

    def doRead(self):
        """
        Called when my socket is ready for reading.
        """
        read = 0
        while read < self.maxThroughput:
            try:
                data, addr = self.socket.recvfrom(self.maxPacketSize)
                read += len(data)
                self.protocol.datagramReceived(data)
            except OSError as se:
                no = se.args[0]
                if no in (EAGAIN, EINTR, EWOULDBLOCK):
                    return
                if no == ECONNREFUSED:
                    self.protocol.connectionRefused()
                else:
                    raise
            except BaseException:
                log.deferr()

    def write(self, data):
        """
        Write a datagram.
        """
        try:
            return self.socket.send(data)
        except OSError as se:
            no = se.args[0]
            if no == EINTR:
                return self.write(data)
            elif no == EMSGSIZE:
                raise error.MessageLengthError("message too long")
            elif no == ECONNREFUSED:
                self.protocol.connectionRefused()
            elif no == EAGAIN:
                # oh, well, drop the data. The only difference from UDP
                # is that UDP won't ever notice.
                # TODO: add TCP-like buffering
                pass
            else:
                raise

    def getPeer(self):
        return address.UNIXAddress(self.remoteaddr)
