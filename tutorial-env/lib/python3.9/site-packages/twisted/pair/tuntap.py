# -*- test-case-name: twisted.pair.test.test_tuntap -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Support for Linux ethernet and IP tunnel devices.

@see: U{https://en.wikipedia.org/wiki/TUN/TAP}
"""

import errno
import fcntl
import os
import platform
import struct
import warnings
from collections import namedtuple
from typing import Tuple

from zope.interface import Attribute, Interface, implementer

from constantly import FlagConstant, Flags  # type: ignore[import]
from incremental import Version

from twisted.internet import abstract, defer, error, interfaces, task
from twisted.pair import ethernet, raw
from twisted.python import log
from twisted.python.deprecate import deprecated
from twisted.python.reflect import fullyQualifiedName
from twisted.python.util import FancyEqMixin, FancyStrMixin

__all__ = [
    "TunnelFlags",
    "TunnelAddress",
    "TuntapPort",
]


_IFNAMSIZ = 16
if (
    platform.machine() == "parisc"
    or platform.machine().startswith("ppc")
    or platform.machine().startswith("sparc")
):  # pragma: no coverage
    # We don't have CI for parisc, hence no coverage is expected.
    _TUNSETIFF = 0x800454CA
    _TUNGETIFF = 0x400454D2
else:
    _TUNSETIFF = 0x400454CA
    _TUNGETIFF = 0x800454D2
_TUN_KO_PATH = b"/dev/net/tun"


class TunnelFlags(Flags):
    """
    L{TunnelFlags} defines more flags which are used to configure the behavior
    of a tunnel device.

    @cvar IFF_TUN: This indicates a I{tun}-type device.  This type of tunnel
        carries IP datagrams.  This flag is mutually exclusive with C{IFF_TAP}.

    @cvar IFF_TAP: This indicates a I{tap}-type device.  This type of tunnel
        carries ethernet frames.  This flag is mutually exclusive with C{IFF_TUN}.

    @cvar IFF_NO_PI: This indicates the I{protocol information} header will
        B{not} be included in data read from the tunnel.

    @see: U{https://www.kernel.org/doc/Documentation/networking/tuntap.txt}
    """

    IFF_TUN = FlagConstant(0x0001)
    IFF_TAP = FlagConstant(0x0002)

    TUN_FASYNC = FlagConstant(0x0010)
    TUN_NOCHECKSUM = FlagConstant(0x0020)
    TUN_NO_PI = FlagConstant(0x0040)
    TUN_ONE_QUEUE = FlagConstant(0x0080)
    TUN_PERSIST = FlagConstant(0x0100)
    TUN_VNET_HDR = FlagConstant(0x0200)

    IFF_NO_PI = FlagConstant(0x1000)
    IFF_ONE_QUEUE = FlagConstant(0x2000)
    IFF_VNET_HDR = FlagConstant(0x4000)
    IFF_TUN_EXCL = FlagConstant(0x8000)


@implementer(interfaces.IAddress)
class TunnelAddress(FancyStrMixin, FancyEqMixin):
    """
    A L{TunnelAddress} represents the tunnel to which a L{TuntapPort} is bound.
    """

    compareAttributes = ("_typeValue", "name")
    showAttributes = (("type", lambda flag: flag.name), "name")

    @property
    def _typeValue(self):
        """
        Return the integer value of the C{type} attribute.  Used to produce
        correct results in the equality implementation.
        """
        # Work-around for https://twistedmatrix.com/trac/ticket/6878
        return self.type.value

    def __init__(self, type, name):
        """
        @param type: Either L{TunnelFlags.IFF_TUN} or L{TunnelFlags.IFF_TAP},
            representing the type of this tunnel.

        @param name: The system name of the tunnel.
        @type name: L{bytes}
        """
        self.type = type
        self.name = name

    def __getitem__(self, index):
        """
        Deprecated accessor for the tunnel name.  Use attributes instead.
        """
        warnings.warn(
            "TunnelAddress.__getitem__ is deprecated since Twisted 14.0.0  "
            "Use attributes instead.",
            category=DeprecationWarning,
            stacklevel=2,
        )
        return ("TUNTAP", self.name)[index]


class _TunnelDescription(namedtuple("_TunnelDescription", "fileno name")):
    """
    Describe an existing tunnel.

    @ivar fileno: the file descriptor associated with the tunnel
    @type fileno: L{int}

    @ivar name: the name of the tunnel
    @type name: L{bytes}
    """


class _IInputOutputSystem(Interface):
    """
    An interface for performing some basic kinds of I/O (particularly that I/O
    which might be useful for L{twisted.pair.tuntap}-using code).
    """

    O_RDWR = Attribute("@see: L{os.O_RDWR}")
    O_NONBLOCK = Attribute("@see: L{os.O_NONBLOCK}")
    O_CLOEXEC = Attribute("@see: L{os.O_CLOEXEC}")

    def open(filename, flag, mode=0o777):
        """
        @see: L{os.open}
        """

    def ioctl(fd, opt, arg=None, mutate_flag=None):
        """
        @see: L{fcntl.ioctl}
        """

    def read(fd, limit):
        """
        @see: L{os.read}
        """

    def write(fd, data):
        """
        @see: L{os.write}
        """

    def close(fd):
        """
        @see: L{os.close}
        """

    def sendUDP(datagram, address):
        """
        Send a datagram to a certain address.

        @param datagram: The payload of a UDP datagram to send.
        @type datagram: L{bytes}

        @param address: The destination to which to send the datagram.
        @type address: L{tuple} of (L{bytes}, L{int})

        @return: The local address from which the datagram was sent.
        @rtype: L{tuple} of (L{bytes}, L{int})
        """

    def receiveUDP(fileno, host, port):
        """
        Return a socket which can be used to receive datagrams sent to the
        given address.

        @param fileno: A file descriptor representing a tunnel device which the
            datagram was either sent via or will be received via.
        @type fileno: L{int}

        @param host: The IPv4 address at which the datagram will be received.
        @type host: L{bytes}

        @param port: The UDP port number at which the datagram will be
            received.
        @type port: L{int}

        @return: A L{socket.socket} which can be used to receive the specified
            datagram.
        """


class _RealSystem:
    """
    An interface to the parts of the operating system which L{TuntapPort}
    relies on.  This is most of an implementation of L{_IInputOutputSystem}.
    """

    open = staticmethod(os.open)
    read = staticmethod(os.read)
    write = staticmethod(os.write)
    close = staticmethod(os.close)
    ioctl = staticmethod(fcntl.ioctl)

    O_RDWR = os.O_RDWR
    O_NONBLOCK = os.O_NONBLOCK
    # Introduced in Python 3.x
    # Ubuntu 12.04, /usr/include/x86_64-linux-gnu/bits/fcntl.h
    O_CLOEXEC = getattr(os, "O_CLOEXEC", 0o2000000)


@implementer(interfaces.IListeningPort)
class TuntapPort(abstract.FileDescriptor):
    """
    A Port that reads and writes packets from/to a TUN/TAP-device.
    """

    maxThroughput = 256 * 1024  # Max bytes we read in one eventloop iteration

    def __init__(self, interface, proto, maxPacketSize=8192, reactor=None, system=None):
        if ethernet.IEthernetProtocol.providedBy(proto):
            self.ethernet = 1
            self._mode = TunnelFlags.IFF_TAP
        else:
            self.ethernet = 0
            self._mode = TunnelFlags.IFF_TUN
            assert raw.IRawPacketProtocol.providedBy(proto)

        if system is None:
            system = _RealSystem()
        self._system = system

        abstract.FileDescriptor.__init__(self, reactor)
        self.interface = interface
        self.protocol = proto
        self.maxPacketSize = maxPacketSize

        logPrefix = self._getLogPrefix(self.protocol)
        self.logstr = f"{logPrefix} ({self._mode.name})"

    def __repr__(self) -> str:
        args: Tuple[str, ...] = (fullyQualifiedName(self.protocol.__class__),)
        if self.connected:
            args = args + ("",)
        else:
            args = args + ("not ",)
        args = args + (self._mode.name, self.interface)
        return "<%s %slistening on %s/%s>" % args

    def startListening(self):
        """
        Create and bind my socket, and begin listening on it.

        This must be called after creating a server to begin listening on the
        specified tunnel.
        """
        self._bindSocket()
        self.protocol.makeConnection(self)
        self.startReading()

    def _openTunnel(self, name, mode):
        """
        Open the named tunnel using the given mode.

        @param name: The name of the tunnel to open.
        @type name: L{bytes}

        @param mode: Flags from L{TunnelFlags} with exactly one of
            L{TunnelFlags.IFF_TUN} or L{TunnelFlags.IFF_TAP} set.

        @return: A L{_TunnelDescription} representing the newly opened tunnel.
        """
        flags = self._system.O_RDWR | self._system.O_CLOEXEC | self._system.O_NONBLOCK
        config = struct.pack("%dsH" % (_IFNAMSIZ,), name, mode.value)
        fileno = self._system.open(_TUN_KO_PATH, flags)
        result = self._system.ioctl(fileno, _TUNSETIFF, config)
        return _TunnelDescription(fileno, result[:_IFNAMSIZ].strip(b"\x00"))

    def _bindSocket(self):
        """
        Open the tunnel.
        """
        log.msg(
            format="%(protocol)s starting on %(interface)s",
            protocol=self.protocol.__class__,
            interface=self.interface,
        )
        try:
            fileno, interface = self._openTunnel(
                self.interface, self._mode | TunnelFlags.IFF_NO_PI
            )
        except OSError as e:
            raise error.CannotListenError(None, self.interface, e)

        self.interface = interface
        self._fileno = fileno

        self.connected = 1

    def fileno(self):
        return self._fileno

    def doRead(self):
        """
        Called when my socket is ready for reading.
        """
        read = 0
        while read < self.maxThroughput:
            try:
                data = self._system.read(self._fileno, self.maxPacketSize)
            except OSError as e:
                if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EINTR):
                    return
                else:
                    raise
            except BaseException:
                raise
            read += len(data)
            # TODO pkt.isPartial()?
            try:
                self.protocol.datagramReceived(data, partial=0)
            except BaseException:
                cls = fullyQualifiedName(self.protocol.__class__)
                log.err(None, f"Unhandled exception from {cls}.datagramReceived")

    def write(self, datagram):
        """
        Write the given data as a single datagram.

        @param datagram: The data that will make up the complete datagram to be
            written.
        @type datagram: L{bytes}
        """
        try:
            return self._system.write(self._fileno, datagram)
        except OSError as e:
            if e.errno == errno.EINTR:
                return self.write(datagram)
            raise

    def writeSequence(self, seq):
        """
        Write a datagram constructed from a L{list} of L{bytes}.

        @param seq: The data that will make up the complete datagram to be
            written.
        @type seq: L{list} of L{bytes}
        """
        self.write(b"".join(seq))

    def stopListening(self):
        """
        Stop accepting connections on this port.

        This will shut down my socket and call self.connectionLost().

        @return: A L{Deferred} that fires when this port has stopped.
        """
        self.stopReading()
        if self.disconnecting:
            return self._stoppedDeferred
        elif self.connected:
            self._stoppedDeferred = task.deferLater(
                self.reactor, 0, self.connectionLost
            )
            self.disconnecting = True
            return self._stoppedDeferred
        else:
            return defer.succeed(None)

    @deprecated(Version("Twisted", 14, 0, 0), stopListening)
    def loseConnection(self):
        """
        Close this tunnel.  Use L{TuntapPort.stopListening} instead.
        """
        self.stopListening().addErrback(log.err)

    def connectionLost(self, reason=None):
        """
        Cleans up my socket.

        @param reason: Ignored.  Do not use this.
        """
        log.msg("(Tuntap %s Closed)" % self.interface)
        abstract.FileDescriptor.connectionLost(self, reason)
        self.protocol.doStop()
        self.connected = 0
        self._system.close(self._fileno)
        self._fileno = -1

    def logPrefix(self):
        """
        Returns the name of my class, to prefix log entries with.
        """
        return self.logstr

    def getHost(self):
        """
        Get the local address of this L{TuntapPort}.

        @return: A L{TunnelAddress} which describes the tunnel device to which
            this object is bound.
        @rtype: L{TunnelAddress}
        """
        return TunnelAddress(self._mode, self.interface)
