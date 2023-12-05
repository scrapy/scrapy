# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tools for automated testing of L{twisted.pair}-based applications.
"""

import socket
import struct
from collections import deque
from errno import EAGAIN, EBADF, EINTR, EINVAL, ENOBUFS, ENOSYS, EPERM, EWOULDBLOCK
from functools import wraps

from zope.interface import implementer

from twisted.internet.protocol import DatagramProtocol
from twisted.pair.ethernet import EthernetProtocol
from twisted.pair.ip import IPProtocol
from twisted.pair.rawudp import RawUDPProtocol
from twisted.pair.tuntap import _IFNAMSIZ, _TUNSETIFF, TunnelFlags, _IInputOutputSystem
from twisted.python.compat import nativeString

# The number of bytes in the "protocol information" header that may be present
# on datagrams read from a tunnel device.  This is two bytes of flags followed
# by two bytes of protocol identification.  All this code does with this
# information is use it to discard the header.
_PI_SIZE = 4


def _H(n):
    """
    Pack an integer into a network-order two-byte string.

    @param n: The integer to pack.  Only values that fit into 16 bits are
        supported.

    @return: The packed representation of the integer.
    @rtype: L{bytes}
    """
    return struct.pack(">H", n)


_IPv4 = 0x0800


def _ethernet(src, dst, protocol, payload):
    """
    Construct an ethernet frame.

    @param src: The source ethernet address, encoded.
    @type src: L{bytes}

    @param dst: The destination ethernet address, encoded.
    @type dst: L{bytes}

    @param protocol: The protocol number of the payload of this datagram.
    @type protocol: L{int}

    @param payload: The content of the ethernet frame (such as an IP datagram).
    @type payload: L{bytes}

    @return: The full ethernet frame.
    @rtype: L{bytes}
    """
    return dst + src + _H(protocol) + payload


def _ip(src, dst, payload):
    """
    Construct an IP datagram with the given source, destination, and
    application payload.

    @param src: The source IPv4 address as a dotted-quad string.
    @type src: L{bytes}

    @param dst: The destination IPv4 address as a dotted-quad string.
    @type dst: L{bytes}

    @param payload: The content of the IP datagram (such as a UDP datagram).
    @type payload: L{bytes}

    @return: An IP datagram header and payload.
    @rtype: L{bytes}
    """
    ipHeader = (
        # Version and header length, 4 bits each
        b"\x45"
        # Differentiated services field
        b"\x00"
        # Total length
        + _H(20 + len(payload))
        + b"\x00\x01\x00\x00\x40\x11"
        # Checksum
        + _H(0)
        # Source address
        + socket.inet_pton(socket.AF_INET, nativeString(src))
        # Destination address
        + socket.inet_pton(socket.AF_INET, nativeString(dst))
    )

    # Total all of the 16-bit integers in the header
    checksumStep1 = sum(struct.unpack("!10H", ipHeader))
    # Pull off the carry
    carry = checksumStep1 >> 16
    # And add it to what was left over
    checksumStep2 = (checksumStep1 & 0xFFFF) + carry
    # Compute the one's complement sum
    checksumStep3 = checksumStep2 ^ 0xFFFF

    # Reconstruct the IP header including the correct checksum so the platform
    # IP stack, if there is one involved in this test, doesn't drop it on the
    # floor as garbage.
    ipHeader = ipHeader[:10] + struct.pack("!H", checksumStep3) + ipHeader[12:]

    return ipHeader + payload


def _udp(src, dst, payload):
    """
    Construct a UDP datagram with the given source, destination, and
    application payload.

    @param src: The source port number.
    @type src: L{int}

    @param dst: The destination port number.
    @type dst: L{int}

    @param payload: The content of the UDP datagram.
    @type payload: L{bytes}

    @return: A UDP datagram header and payload.
    @rtype: L{bytes}
    """
    udpHeader = (
        # Source port
        _H(src)
        # Destination port
        + _H(dst)
        # Length
        + _H(len(payload) + 8)
        # Checksum
        + _H(0)
    )
    return udpHeader + payload


class Tunnel:
    """
    An in-memory implementation of a tun or tap device.

    @cvar _DEVICE_NAME: A string representing the conventional filesystem entry
        for the tunnel factory character special device.
    @type _DEVICE_NAME: C{bytes}
    """

    _DEVICE_NAME = b"/dev/net/tun"

    # Between POSIX and Python, there are 4 combinations.  Here are two, at
    # least.
    EAGAIN_STYLE = IOError(EAGAIN, "Resource temporarily unavailable")
    EWOULDBLOCK_STYLE = OSError(EWOULDBLOCK, "Operation would block")

    # Oh yea, and then there's the case where maybe we would've read, but
    # someone sent us a signal instead.
    EINTR_STYLE = IOError(EINTR, "Interrupted function call")

    nonBlockingExceptionStyle = EAGAIN_STYLE

    SEND_BUFFER_SIZE = 1024

    def __init__(self, system, openFlags, fileMode):
        """
        @param system: An L{_IInputOutputSystem} provider to use to perform I/O.

        @param openFlags: Any flags to apply when opening the tunnel device.
            See C{os.O_*}.

        @type openFlags: L{int}

        @param fileMode: ignored
        """
        self.system = system

        # Drop fileMode on the floor - evidence and logic suggest it is
        # irrelevant with respect to /dev/net/tun
        self.openFlags = openFlags
        self.tunnelMode = None
        self.requestedName = None
        self.name = None
        self.readBuffer = deque()
        self.writeBuffer = deque()
        self.pendingSignals = deque()

    @property
    def blocking(self):
        """
        If the file descriptor for this tunnel is open in blocking mode,
        C{True}.  C{False} otherwise.
        """
        return not (self.openFlags & self.system.O_NONBLOCK)

    @property
    def closeOnExec(self):
        """
        If the file descriptor for this tunnel is marked as close-on-exec,
        C{True}.  C{False} otherwise.
        """
        return bool(self.openFlags & self.system.O_CLOEXEC)

    def addToReadBuffer(self, datagram):
        """
        Deliver a datagram to this tunnel's read buffer.  This makes it
        available to be read later using the C{read} method.

        @param datagram: The IPv4 datagram to deliver.  If the mode of this
            tunnel is TAP then ethernet framing will be added automatically.
        @type datagram: L{bytes}
        """
        # TAP devices also include ethernet framing.
        if self.tunnelMode & TunnelFlags.IFF_TAP.value:
            datagram = _ethernet(
                src=b"\x00" * 6, dst=b"\xff" * 6, protocol=_IPv4, payload=datagram
            )

        self.readBuffer.append(datagram)

    def read(self, limit):
        """
        Read a datagram out of this tunnel.

        @param limit: The maximum number of bytes from the datagram to return.
            If the next datagram is larger than this, extra bytes are dropped
            and lost forever.
        @type limit: L{int}

        @raise OSError: Any of the usual I/O problems can result in this
            exception being raised with some particular error number set.

        @raise IOError: Any of the usual I/O problems can result in this
            exception being raised with some particular error number set.

        @return: The datagram which was read from the tunnel.  If the tunnel
            mode does not include L{TunnelFlags.IFF_NO_PI} then the datagram is
            prefixed with a 4 byte PI header.
        @rtype: L{bytes}
        """
        if self.readBuffer:
            if self.tunnelMode & TunnelFlags.IFF_NO_PI.value:
                header = b""
            else:
                # Synthesize a PI header to include in the result.  Nothing in
                # twisted.pair uses the PI information yet so we can synthesize
                # something incredibly boring (ie 32 bits of 0).
                header = b"\x00" * _PI_SIZE
                limit -= 4
            return header + self.readBuffer.popleft()[:limit]
        elif self.blocking:
            raise NotImplementedError()
        else:
            raise self.nonBlockingExceptionStyle

    def write(self, datagram):
        """
        Write a datagram into this tunnel.

        @param datagram: The datagram to write.
        @type datagram: L{bytes}

        @raise IOError: Any of the usual I/O problems can result in this
            exception being raised with some particular error number set.

        @return: The number of bytes of the datagram which were written.
        @rtype: L{int}
        """
        if self.pendingSignals:
            self.pendingSignals.popleft()
            raise OSError(EINTR, "Interrupted system call")

        if len(datagram) > self.SEND_BUFFER_SIZE:
            raise OSError(ENOBUFS, "No buffer space available")

        self.writeBuffer.append(datagram)
        return len(datagram)


def _privileged(original):
    """
    Wrap a L{MemoryIOSystem} method with permission-checking logic.  The
    returned function will check C{self.permissions} and raise L{IOError} with
    L{errno.EPERM} if the function name is not listed as an available
    permission.

    @param original: The L{MemoryIOSystem} instance to wrap.

    @return: A wrapper around C{original} that applies permission checks.
    """

    @wraps(original)
    def permissionChecker(self, *args, **kwargs):
        if original.__name__ not in self.permissions:
            raise OSError(EPERM, "Operation not permitted")
        return original(self, *args, **kwargs)

    return permissionChecker


@implementer(_IInputOutputSystem)
class MemoryIOSystem:
    """
    An in-memory implementation of basic I/O primitives, useful in the context
    of unit testing as a drop-in replacement for parts of the C{os} module.

    @ivar _devices:
    @ivar _openFiles:
    @ivar permissions:

    @ivar _counter:
    """

    _counter = 8192

    O_RDWR = 1 << 0
    O_NONBLOCK = 1 << 1
    O_CLOEXEC = 1 << 2

    def __init__(self):
        self._devices = {}
        self._openFiles = {}
        self.permissions = {"open", "ioctl"}

    def getTunnel(self, port):
        """
        Get the L{Tunnel} object associated with the given L{TuntapPort}.

        @param port: A L{TuntapPort} previously initialized using this
            L{MemoryIOSystem}.

        @return: The tunnel object created by a prior use of C{open} on this
            object on the tunnel special device file.
        @rtype: L{Tunnel}
        """
        return self._openFiles[port.fileno()]

    def registerSpecialDevice(self, name, cls):
        """
        Specify a class which will be used to handle I/O to a device of a
        particular name.

        @param name: The filesystem path name of the device.
        @type name: L{bytes}

        @param cls: A class (like L{Tunnel}) to instantiated whenever this
            device is opened.
        """
        self._devices[name] = cls

    @_privileged
    def open(self, name, flags, mode=None):
        """
        A replacement for C{os.open}.  This initializes state in this
        L{MemoryIOSystem} which will be reflected in the behavior of the other
        file descriptor-related methods (eg L{MemoryIOSystem.read},
        L{MemoryIOSystem.write}, etc).

        @param name: A string giving the name of the file to open.
        @type name: C{bytes}

        @param flags: The flags with which to open the file.
        @type flags: C{int}

        @param mode: The mode with which to open the file.
        @type mode: C{int}

        @raise OSError: With C{ENOSYS} if the file is not a recognized special
            device file.

        @return: A file descriptor associated with the newly opened file
            description.
        @rtype: L{int}
        """
        if name in self._devices:
            fd = self._counter
            self._counter += 1
            self._openFiles[fd] = self._devices[name](self, flags, mode)
            return fd
        raise OSError(ENOSYS, "Function not implemented")

    def read(self, fd, limit):
        """
        Try to read some bytes out of one of the in-memory buffers which may
        previously have been populated by C{write}.

        @see: L{os.read}
        """
        try:
            return self._openFiles[fd].read(limit)
        except KeyError:
            raise OSError(EBADF, "Bad file descriptor")

    def write(self, fd, data):
        """
        Try to add some bytes to one of the in-memory buffers to be accessed by
        a later C{read} call.

        @see: L{os.write}
        """
        try:
            return self._openFiles[fd].write(data)
        except KeyError:
            raise OSError(EBADF, "Bad file descriptor")

    def close(self, fd):
        """
        Discard the in-memory buffer and other in-memory state for the given
        file descriptor.

        @see: L{os.close}
        """
        try:
            del self._openFiles[fd]
        except KeyError:
            raise OSError(EBADF, "Bad file descriptor")

    @_privileged
    def ioctl(self, fd, request, args):
        """
        Perform some configuration change to the in-memory state for the given
        file descriptor.

        @see: L{fcntl.ioctl}
        """
        try:
            tunnel = self._openFiles[fd]
        except KeyError:
            raise OSError(EBADF, "Bad file descriptor")

        if request != _TUNSETIFF:
            raise OSError(EINVAL, "Request or args is not valid.")

        name, mode = struct.unpack("%dsH" % (_IFNAMSIZ,), args)
        tunnel.tunnelMode = mode
        tunnel.requestedName = name
        tunnel.name = name[: _IFNAMSIZ - 3] + b"123"

        return struct.pack("%dsH" % (_IFNAMSIZ,), tunnel.name, mode)

    def sendUDP(self, datagram, address):
        """
        Write an ethernet frame containing an ip datagram containing a udp
        datagram containing the given payload, addressed to the given address,
        to a tunnel device previously opened on this I/O system.

        @param datagram: A UDP datagram payload to send.
        @type datagram: L{bytes}

        @param address: The destination to which to send the datagram.
        @type address: L{tuple} of (L{bytes}, L{int})

        @return: A two-tuple giving the address from which gives the address
            from which the datagram was sent.
        @rtype: L{tuple} of (L{bytes}, L{int})
        """
        # Just make up some random thing
        srcIP = "10.1.2.3"
        srcPort = 21345

        serialized = _ip(
            src=srcIP,
            dst=address[0],
            payload=_udp(src=srcPort, dst=address[1], payload=datagram),
        )

        openFiles = list(self._openFiles.values())
        openFiles[0].addToReadBuffer(serialized)

        return (srcIP, srcPort)

    def receiveUDP(self, fileno, host, port):
        """
        Get a socket-like object which can be used to receive a datagram sent
        from the given address.

        @param fileno: A file descriptor representing a tunnel device which the
            datagram will be received via.
        @type fileno: L{int}

        @param host: The IPv4 address to which the datagram was sent.
        @type host: L{bytes}

        @param port: The UDP port number to which the datagram was sent.
            received.
        @type port: L{int}

        @return: A L{socket.socket}-like object which can be used to receive
            the specified datagram.
        """
        return _FakePort(self, fileno)


class _FakePort:
    """
    A socket-like object which can be used to read UDP datagrams from
    tunnel-like file descriptors managed by a L{MemoryIOSystem}.
    """

    def __init__(self, system, fileno):
        self._system = system
        self._fileno = fileno

    def recv(self, nbytes):
        """
        Receive a datagram sent to this port using the L{MemoryIOSystem} which
        created this object.

        This behaves like L{socket.socket.recv} but the data being I{sent} and
        I{received} only passes through various memory buffers managed by this
        object and L{MemoryIOSystem}.

        @see: L{socket.socket.recv}
        """
        data = self._system._openFiles[self._fileno].writeBuffer.popleft()

        datagrams = []
        receiver = DatagramProtocol()

        def capture(datagram, address):
            datagrams.append(datagram)

        receiver.datagramReceived = capture

        udp = RawUDPProtocol()
        udp.addProto(12345, receiver)

        ip = IPProtocol()
        ip.addProto(17, udp)

        mode = self._system._openFiles[self._fileno].tunnelMode
        if mode & TunnelFlags.IFF_TAP.value:
            ether = EthernetProtocol()
            ether.addProto(0x800, ip)
            datagramReceived = ether.datagramReceived
        else:
            datagramReceived = lambda data: ip.datagramReceived(
                data, None, None, None, None
            )

        dataHasPI = not (mode & TunnelFlags.IFF_NO_PI.value)

        if dataHasPI:
            # datagramReceived can't handle the PI, get rid of it.
            data = data[_PI_SIZE:]

        datagramReceived(data)
        return datagrams[0][:nbytes]
