# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.pair.tuntap}.
"""


import os
import socket
import struct
from collections import deque
from errno import EAGAIN, EBADF, EINVAL, ENODEV, ENOENT, EPERM, EWOULDBLOCK
from itertools import cycle
from random import randrange
from signal import SIGINT
from typing import Optional

from twisted.python.reflect import ObjectNotFound, namedAny

platformSkip: Optional[str]
try:
    namedAny("fcntl.ioctl")
except (ObjectNotFound, AttributeError):
    platformSkip = "Platform is missing fcntl/ioctl support"
else:
    platformSkip = None

from zope.interface import Interface, implementer
from zope.interface.verify import verifyObject

from twisted.internet.error import CannotListenError
from twisted.internet.interfaces import IAddress, IListeningPort, IReactorFDSet
from twisted.internet.protocol import (
    AbstractDatagramProtocol,
    DatagramProtocol,
    Factory,
)
from twisted.internet.task import Clock
from twisted.pair.ethernet import EthernetProtocol
from twisted.pair.ip import IPProtocol
from twisted.pair.raw import IRawPacketProtocol
from twisted.pair.rawudp import RawUDPProtocol
from twisted.python.compat import iterbytes
from twisted.python.log import addObserver, removeObserver, textFromEventDict
from twisted.python.reflect import fullyQualifiedName
from twisted.trial.unittest import SkipTest, SynchronousTestCase

# Let the module-scope testing subclass of this still be defined (and then not
# used) in case we can't import from twisted.pair.testing due to platform
# limitations.
_RealSystem = object

# Same rationale as for _RealSystem.
_IInputOutputSystem = Interface


if not platformSkip:
    from twisted.pair.testing import (
        _H,
        _PI_SIZE,
        MemoryIOSystem,
        Tunnel,
        _ethernet,
        _ip,
        _IPv4,
        _udp,
    )
    from twisted.pair.tuntap import (
        _IFNAMSIZ,
        _TUNSETIFF,
        TunnelAddress,
        TunnelFlags,
        TuntapPort,
        _IInputOutputSystem,
        _RealSystem,
    )
else:
    skip = platformSkip


@implementer(IReactorFDSet)
class ReactorFDSet:
    """
    An implementation of L{IReactorFDSet} which only keeps track of which
    descriptors have been registered for reading and writing.

    This implementation isn't actually capable of determining readability or
    writeability and generates no events for the descriptors registered with
    it.

    @ivar _readers: A L{set} of L{IReadDescriptor} providers which the reactor
        is supposedly monitoring for read events.

    @ivar _writers: A L{set} of L{IWriteDescriptor} providers which the reactor
        is supposedly monitoring for write events.
    """

    def __init__(self):
        self._readers = set()
        self._writers = set()
        self.addReader = self._readers.add
        self.addWriter = self._writers.add

    def removeReader(self, reader):
        self._readers.discard(reader)

    def removeWriter(self, writer):
        self._writers.discard(writer)

    def getReaders(self):
        return iter(self._readers)

    def getWriters(self):
        return iter(self._writers)

    def removeAll(self):
        try:
            return list(self._readers | self._writers)
        finally:
            self._readers = set()
            self._writers = set()


verifyObject(IReactorFDSet, ReactorFDSet())


class FSSetClock(Clock, ReactorFDSet):
    """
    An L{FSSetClock} is a L{IReactorFDSet} and an L{IReactorClock}.
    """

    def __init__(self):
        Clock.__init__(self)
        ReactorFDSet.__init__(self)


class TunHelper:
    """
    A helper for tests of tun-related functionality (ip-level tunnels).
    """

    @property
    def TUNNEL_TYPE(self):
        # Hide this in a property because TunnelFlags is not always imported.
        return TunnelFlags.IFF_TUN | TunnelFlags.IFF_NO_PI

    def __init__(self, tunnelRemote, tunnelLocal):
        """
        @param tunnelRemote: The source address for UDP datagrams originated
            from this helper.  This is an IPv4 dotted-quad string.
        @type tunnelRemote: L{bytes}

        @param tunnelLocal: The destination address for UDP datagrams
            originated from this helper.  This is an IPv4 dotted-quad string.
        @type tunnelLocal: L{bytes}
        """
        self.tunnelRemote = tunnelRemote
        self.tunnelLocal = tunnelLocal

    def encapsulate(self, source, destination, payload):
        """
        Construct an ip datagram containing a udp datagram containing the given
        application-level payload.

        @param source: The source port for the UDP datagram being encapsulated.
        @type source: L{int}

        @param destination: The destination port for the UDP datagram being
            encapsulated.
        @type destination: L{int}

        @param payload: The application data to include in the udp datagram.
        @type payload: L{bytes}

        @return: An ethernet frame.
        @rtype: L{bytes}
        """
        return _ip(
            src=self.tunnelRemote,
            dst=self.tunnelLocal,
            payload=_udp(src=source, dst=destination, payload=payload),
        )

    def parser(self):
        """
        Get a function for parsing a datagram read from a I{tun} device.

        @return: A function which accepts a datagram exactly as might be read
            from a I{tun} device.  The datagram is expected to ultimately carry
            a UDP datagram.  When called, it returns a L{list} of L{tuple}s.
            Each tuple has the UDP application data as the first element and
            the sender address as the second element.
        """
        datagrams = []
        receiver = DatagramProtocol()

        def capture(*args):
            datagrams.append(args)

        receiver.datagramReceived = capture

        udp = RawUDPProtocol()
        udp.addProto(12345, receiver)

        ip = IPProtocol()
        ip.addProto(17, udp)

        def parse(data):
            # TUN devices omit the ethernet framing so we can start parsing
            # right at the IP layer.
            ip.datagramReceived(data, False, None, None, None)
            return datagrams

        return parse


class TapHelper:
    """
    A helper for tests of tap-related functionality (ethernet-level tunnels).
    """

    @property
    def TUNNEL_TYPE(self):
        flag = TunnelFlags.IFF_TAP
        if not self.pi:
            flag |= TunnelFlags.IFF_NO_PI
        return flag

    def __init__(self, tunnelRemote, tunnelLocal, pi):
        """
        @param tunnelRemote: The source address for UDP datagrams originated
            from this helper.  This is an IPv4 dotted-quad string.
        @type tunnelRemote: L{bytes}

        @param tunnelLocal: The destination address for UDP datagrams
            originated from this helper.  This is an IPv4 dotted-quad string.
        @type tunnelLocal: L{bytes}

        @param pi: A flag indicating whether this helper will generate and
            consume a protocol information (PI) header.
        @type pi: L{bool}
        """
        self.tunnelRemote = tunnelRemote
        self.tunnelLocal = tunnelLocal
        self.pi = pi

    def encapsulate(self, source, destination, payload):
        """
        Construct an ethernet frame containing an ip datagram containing a udp
        datagram containing the given application-level payload.

        @param source: The source port for the UDP datagram being encapsulated.
        @type source: L{int}

        @param destination: The destination port for the UDP datagram being
            encapsulated.
        @type destination: L{int}

        @param payload: The application data to include in the udp datagram.
        @type payload: L{bytes}

        @return: An ethernet frame.
        @rtype: L{bytes}
        """
        tun = TunHelper(self.tunnelRemote, self.tunnelLocal)
        ip = tun.encapsulate(source, destination, payload)
        frame = _ethernet(
            src=b"\x00\x00\x00\x00\x00\x00",
            dst=b"\xff\xff\xff\xff\xff\xff",
            protocol=_IPv4,
            payload=ip,
        )
        if self.pi:
            # Going to send a datagram using IPv4 addressing
            protocol = _IPv4
            # There are no flags though
            flags = 0
            frame = _H(flags) + _H(protocol) + frame
        return frame

    def parser(self):
        """
        Get a function for parsing a datagram read from a I{tap} device.

        @return: A function which accepts a datagram exactly as might be read
            from a I{tap} device.  The datagram is expected to ultimately carry
            a UDP datagram.  When called, it returns a L{list} of L{tuple}s.
            Each tuple has the UDP application data as the first element and
            the sender address as the second element.
        """
        datagrams = []
        receiver = DatagramProtocol()

        def capture(*args):
            datagrams.append(args)

        receiver.datagramReceived = capture

        udp = RawUDPProtocol()
        udp.addProto(12345, receiver)

        ip = IPProtocol()
        ip.addProto(17, udp)

        ether = EthernetProtocol()
        ether.addProto(0x800, ip)

        def parser(datagram):
            # TAP devices might include a PI header.  Strip that off if we
            # expect it to be there.
            if self.pi:
                datagram = datagram[_PI_SIZE:]

            # TAP devices include ethernet framing so start parsing at the
            # ethernet layer.
            ether.datagramReceived(datagram)
            return datagrams

        return parser


class TunnelTests(SynchronousTestCase):
    """
    L{Tunnel} is mostly tested by other test cases but some tests don't fit
    there.  Those tests are here.
    """

    def test_blockingRead(self):
        """
        Blocking reads are not implemented by L{Tunnel.read}.  Attempting one
        results in L{NotImplementedError} being raised.
        """
        tunnel = Tunnel(MemoryIOSystem(), os.O_RDONLY, None)
        self.assertRaises(NotImplementedError, tunnel.read, 1024)


class TunnelDeviceTestsMixin:
    """
    A mixin defining tests that apply to L{_IInputOutputSystem}
    implementations.
    """

    def setUp(self):
        """
        Create the L{_IInputOutputSystem} provider under test and open a tunnel
        using it.
        """
        self.system = self.createSystem()
        self.fileno = self.system.open(b"/dev/net/tun", os.O_RDWR | os.O_NONBLOCK)
        self.addCleanup(self.system.close, self.fileno)

        mode = self.helper.TUNNEL_TYPE
        config = struct.pack("%dsH" % (_IFNAMSIZ,), self._TUNNEL_DEVICE, mode.value)
        self.system.ioctl(self.fileno, _TUNSETIFF, config)

    def test_interface(self):
        """
        The object under test provides L{_IInputOutputSystem}.
        """
        self.assertTrue(verifyObject(_IInputOutputSystem, self.system))

    def _invalidFileDescriptor(self):
        """
        Get an invalid file descriptor.

        @return: An integer which is not a valid file descriptor at the time of
            this call.  After any future system call which allocates a new file
            descriptor, there is no guarantee the returned file descriptor will
            still be invalid.
        """
        fd = self.system.open(b"/dev/net/tun", os.O_RDWR)
        self.system.close(fd)
        return fd

    def test_readEBADF(self):
        """
        The device's C{read} implementation raises L{OSError} with an errno of
        C{EBADF} when called on a file descriptor which is not valid (ie, which
        has no associated file description).
        """
        fd = self._invalidFileDescriptor()
        exc = self.assertRaises(OSError, self.system.read, fd, 1024)
        self.assertEqual(EBADF, exc.errno)

    def test_writeEBADF(self):
        """
        The device's C{write} implementation raises L{OSError} with an errno of
        C{EBADF} when called on a file descriptor which is not valid (ie, which
        has no associated file description).
        """
        fd = self._invalidFileDescriptor()
        exc = self.assertRaises(OSError, self.system.write, fd, b"bytes")
        self.assertEqual(EBADF, exc.errno)

    def test_closeEBADF(self):
        """
        The device's C{close} implementation raises L{OSError} with an errno of
        C{EBADF} when called on a file descriptor which is not valid (ie, which
        has no associated file description).
        """
        fd = self._invalidFileDescriptor()
        exc = self.assertRaises(OSError, self.system.close, fd)
        self.assertEqual(EBADF, exc.errno)

    def test_ioctlEBADF(self):
        """
        The device's C{ioctl} implementation raises L{OSError} with an errno of
        C{EBADF} when called on a file descriptor which is not valid (ie, which
        has no associated file description).
        """
        fd = self._invalidFileDescriptor()
        exc = self.assertRaises(IOError, self.system.ioctl, fd, _TUNSETIFF, b"tap0")
        self.assertEqual(EBADF, exc.errno)

    def test_ioctlEINVAL(self):
        """
        The device's C{ioctl} implementation raises L{IOError} with an errno of
        C{EINVAL} when called with a request (second argument) which is not a
        supported operation.
        """
        # Try to invent an unsupported request.  Hopefully this isn't a real
        # request on any system.
        request = 0xDEADBEEF
        exc = self.assertRaises(
            IOError, self.system.ioctl, self.fileno, request, b"garbage"
        )
        self.assertEqual(EINVAL, exc.errno)

    def test_receive(self):
        """
        If a UDP datagram is sent to an address reachable by the tunnel device
        then it can be read out of the tunnel device.
        """
        parse = self.helper.parser()

        found = False

        # Try sending the datagram a lot of times.  There are no delivery
        # guarantees for UDP - not even over localhost.
        for i in range(100):
            key = randrange(2 ** 64)
            message = b"hello world:%d" % (key,)
            source = self.system.sendUDP(message, (self._TUNNEL_REMOTE, 12345))

            # Likewise try receiving each of those datagrams a lot of times.
            # Timing might cause us to miss it the first few dozen times
            # through the loop.
            for j in range(100):
                try:
                    packet = self.system.read(self.fileno, 1024)
                except OSError as e:
                    if e.errno in (EAGAIN, EWOULDBLOCK):
                        break
                    raise
                else:
                    datagrams = parse(packet)
                    if (message, source) in datagrams:
                        found = True
                        break
                    del datagrams[:]
            if found:
                break

        if not found:
            self.fail("Never saw probe UDP packet on tunnel")

    def test_send(self):
        """
        If a UDP datagram is written the tunnel device then it is received by
        the network to which it is addressed.
        """
        # Construct a unique application payload so the receiving side can
        # unambiguously identify the datagram we sent.
        key = randrange(2 ** 64)
        message = b"hello world:%d" % (key,)

        # To avoid really inconvenient test failures where the test just hangs
        # forever, set up a timeout for blocking socket operations.  This
        # shouldn't ever be triggered when the test is passing.  It only serves
        # to make sure the test runs eventually completes if something is
        # broken in a way that prevents real traffic from flowing.  The value
        # chosen is totally arbitrary (but it might coincidentally exactly
        # match trial's builtin timeout for asynchronous tests).
        self.addCleanup(socket.setdefaulttimeout, socket.getdefaulttimeout())
        socket.setdefaulttimeout(120)

        # Start listening for the test datagram first.  The resulting port
        # object can be used to receive datagrams sent to _TUNNEL_LOCAL:12345 -
        # in other words, an application using the tunnel device will be able
        # to cause datagrams to arrive at this port as though they actually
        # traversed a network to arrive at this host.
        port = self.system.receiveUDP(self.fileno, self._TUNNEL_LOCAL, 12345)

        # Construct a packet with the appropriate wrappers and headings so that
        # it will arrive at the port created above.
        packet = self.helper.encapsulate(50000, 12345, message)

        # Write the packet to the tunnel device.
        self.system.write(self.fileno, packet)

        # Try to receive that datagram and verify it has the correct payload.
        packet = port.recv(1024)
        self.assertEqual(message, packet)


class FakeDeviceTestsMixin:
    """
    Define a mixin for use with test cases that require an
    L{_IInputOutputSystem} provider.  This mixin hands out L{MemoryIOSystem}
    instances as the provider of that interface.
    """

    _TUNNEL_DEVICE = b"tap-twistedtest"
    _TUNNEL_LOCAL = b"172.16.2.1"
    _TUNNEL_REMOTE = b"172.16.2.2"

    def createSystem(self):
        """
        Create and return a brand new L{MemoryIOSystem}.

        The L{MemoryIOSystem} knows how to open new tunnel devices.

        @return: The newly created I/O system object.
        @rtype: L{MemoryIOSystem}
        """
        system = MemoryIOSystem()
        system.registerSpecialDevice(Tunnel._DEVICE_NAME, Tunnel)
        return system


class FakeTapDeviceTests(
    FakeDeviceTestsMixin, TunnelDeviceTestsMixin, SynchronousTestCase
):
    """
    Run various tap-type tunnel unit tests against an in-memory I/O system.
    """


setattr(
    FakeTapDeviceTests,
    "helper",
    TapHelper(
        FakeTapDeviceTests._TUNNEL_REMOTE, FakeTapDeviceTests._TUNNEL_LOCAL, pi=False
    ),
)


class FakeTapDeviceWithPITests(
    FakeDeviceTestsMixin, TunnelDeviceTestsMixin, SynchronousTestCase
):
    """
    Run various tap-type tunnel unit tests against an in-memory I/O system with
    the PI header enabled.
    """


setattr(
    FakeTapDeviceWithPITests,
    "helper",
    TapHelper(
        FakeTapDeviceTests._TUNNEL_REMOTE, FakeTapDeviceTests._TUNNEL_LOCAL, pi=True
    ),
)


class FakeTunDeviceTests(
    FakeDeviceTestsMixin, TunnelDeviceTestsMixin, SynchronousTestCase
):
    """
    Run various tun-type tunnel unit tests against an in-memory I/O system.
    """


setattr(
    FakeTunDeviceTests,
    "helper",
    TunHelper(FakeTunDeviceTests._TUNNEL_REMOTE, FakeTunDeviceTests._TUNNEL_LOCAL),
)


@implementer(_IInputOutputSystem)
class TestRealSystem(_RealSystem):
    """
    Add extra skipping logic so tests that try to create real tunnel devices on
    platforms where those are not supported automatically get skipped.
    """

    def open(self, filename, *args, **kwargs):
        """
        Attempt an open, but if the file is /dev/net/tun and it does not exist,
        translate the error into L{SkipTest} so that tests that require
        platform support for tuntap devices are skipped instead of failed.
        """
        try:
            return super().open(filename, *args, **kwargs)
        except OSError as e:
            # The device file may simply be missing.  The device file may also
            # exist but be unsupported by the kernel.
            if e.errno in (ENOENT, ENODEV) and filename == b"/dev/net/tun":
                raise SkipTest("Platform lacks /dev/net/tun")
            raise

    def ioctl(self, *args, **kwargs):
        """
        Attempt an ioctl, but translate permission denied errors into
        L{SkipTest} so that tests that require elevated system privileges and
        do not have them are skipped instead of failed.
        """
        try:
            return super().ioctl(*args, **kwargs)
        except OSError as e:
            if EPERM == e.errno:
                raise SkipTest("Permission to configure device denied")
            raise

    def sendUDP(self, datagram, address):
        """
        Use the platform network stack to send a datagram to the given address.

        @param datagram: A UDP datagram payload to send.
        @type datagram: L{bytes}

        @param address: The destination to which to send the datagram.
        @type address: L{tuple} of (L{bytes}, L{int})

        @return: The address from which the UDP datagram was sent.
        @rtype: L{tuple} of (L{bytes}, L{int})
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("172.16.0.1", 0))
        s.sendto(datagram, address)
        return s.getsockname()

    def receiveUDP(self, fileno, host, port):
        """
        Use the platform network stack to receive a datagram sent to the given
        address.

        @param fileno: The file descriptor of the tunnel used to send the
            datagram.  This is ignored because a real socket is used to receive
            the datagram.
        @type fileno: L{int}

        @param host: The IPv4 address at which the datagram will be received.
        @type host: L{bytes}

        @param port: The UDP port number at which the datagram will be
            received.
        @type port: L{int}

        @return: A L{socket.socket} which can be used to receive the specified
            datagram.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((host, port))
        return s


class RealDeviceTestsMixin:
    """
    Define a mixin for use with test cases that require an
    L{_IInputOutputSystem} provider.  This mixin hands out L{TestRealSystem}
    instances as the provider of that interface.
    """

    skip = platformSkip

    def createSystem(self):
        """
        Create a real I/O system that can be used to open real tunnel device
        provided by the underlying system and previously configured.

        @return: The newly created I/O system object.
        @rtype: L{TestRealSystem}
        """
        return TestRealSystem()


class RealDeviceWithProtocolInformationTests(
    RealDeviceTestsMixin, TunnelDeviceTestsMixin, SynchronousTestCase
):
    """
    Run various tap-type tunnel unit tests, with "protocol information" (PI)
    turned on, against a real I/O system.
    """

    _TUNNEL_DEVICE = b"tap-twtest-pi"
    _TUNNEL_LOCAL = b"172.16.1.1"
    _TUNNEL_REMOTE = b"172.16.1.2"

    # The PI flag is not an inherent part of the tunnel.  It must be specified
    # by each user of the tunnel.  Thus, we must also have an indication of
    # whether we want PI so the tests can properly initialize the tunnel
    # device.
    helper = TapHelper(_TUNNEL_REMOTE, _TUNNEL_LOCAL, pi=True)


class RealDeviceWithoutProtocolInformationTests(
    RealDeviceTestsMixin, TunnelDeviceTestsMixin, SynchronousTestCase
):

    """
    Run various tap-type tunnel unit tests, with "protocol information" (PI)
    turned off, against a real I/O system.
    """

    _TUNNEL_DEVICE = b"tap-twtest"
    _TUNNEL_LOCAL = b"172.16.0.1"
    _TUNNEL_REMOTE = b"172.16.0.2"

    helper = TapHelper(_TUNNEL_REMOTE, _TUNNEL_LOCAL, pi=False)


class TuntapPortTests(SynchronousTestCase):
    """
    Tests for L{TuntapPort} behavior that is independent of the tunnel type.
    """

    def test_interface(self):
        """
        A L{TuntapPort} instance provides L{IListeningPort}.
        """
        port = TuntapPort(b"device", EthernetProtocol())
        self.assertTrue(verifyObject(IListeningPort, port))

    def test_realSystem(self):
        """
        When not initialized with an I/O system, L{TuntapPort} uses a
        L{_RealSystem}.
        """
        port = TuntapPort(b"device", EthernetProtocol())
        self.assertIsInstance(port._system, _RealSystem)


class TunnelTestsMixin:
    """
    A mixin defining tests for L{TuntapPort}.

    These tests run against L{MemoryIOSystem} (proven equivalent to the real
    thing by the tests above) to avoid performing any real I/O.
    """

    def setUp(self):
        """
        Create an in-memory I/O system and set up a L{TuntapPort} against it.
        """
        self.name = b"tun0"
        self.system = MemoryIOSystem()
        self.system.registerSpecialDevice(Tunnel._DEVICE_NAME, Tunnel)
        self.protocol = self.factory.buildProtocol(
            TunnelAddress(self.helper.TUNNEL_TYPE, self.name)
        )
        self.reactor = FSSetClock()
        self.port = TuntapPort(
            self.name, self.protocol, reactor=self.reactor, system=self.system
        )

    def _tunnelTypeOnly(self, flags):
        """
        Mask off any flags except for L{TunnelType.IFF_TUN} and
        L{TunnelType.IFF_TAP}.

        @param flags: Flags from L{TunnelType} to mask.
        @type flags: L{FlagConstant}

        @return: The flags given by C{flags} except the two type flags.
        @rtype: L{FlagConstant}
        """
        return flags & (TunnelFlags.IFF_TUN | TunnelFlags.IFF_TAP)

    def test_startListeningOpensDevice(self):
        """
        L{TuntapPort.startListening} opens the tunnel factory character special
        device C{"/dev/net/tun"} and configures it as a I{tun} tunnel.
        """
        system = self.system
        self.port.startListening()
        tunnel = self.system.getTunnel(self.port)

        expected = (
            system.O_RDWR | system.O_CLOEXEC | system.O_NONBLOCK,
            b"tun0" + b"\x00" * (_IFNAMSIZ - len(b"tun0")),
            self.port.interface,
            False,
            True,
        )
        actual = (
            tunnel.openFlags,
            tunnel.requestedName,
            tunnel.name,
            tunnel.blocking,
            tunnel.closeOnExec,
        )
        self.assertEqual(expected, actual)

    def test_startListeningSetsConnected(self):
        """
        L{TuntapPort.startListening} sets C{connected} on the port object to
        C{True}.
        """
        self.port.startListening()
        self.assertTrue(self.port.connected)

    def test_startListeningConnectsProtocol(self):
        """
        L{TuntapPort.startListening} calls C{makeConnection} on the protocol
        the port was initialized with, passing the port as an argument.
        """
        self.port.startListening()
        self.assertIs(self.port, self.protocol.transport)

    def test_startListeningStartsReading(self):
        """
        L{TuntapPort.startListening} passes the port instance to the reactor's
        C{addReader} method to begin watching the port's file descriptor for
        data to read.
        """
        self.port.startListening()
        self.assertIn(self.port, self.reactor.getReaders())

    def test_startListeningHandlesOpenFailure(self):
        """
        L{TuntapPort.startListening} raises L{CannotListenError} if opening the
        tunnel factory character special device fails.
        """
        self.system.permissions.remove("open")
        self.assertRaises(CannotListenError, self.port.startListening)

    def test_startListeningHandlesConfigureFailure(self):
        """
        L{TuntapPort.startListening} raises L{CannotListenError} if the
        C{ioctl} call to configure the tunnel device fails.
        """
        self.system.permissions.remove("ioctl")
        self.assertRaises(CannotListenError, self.port.startListening)

    def _stopPort(self, port):
        """
        Verify that the C{stopListening} method of an L{IListeningPort} removes
        that port from the reactor's "readers" set and also that the
        L{Deferred} returned by that method fires with L{None}.

        @param port: The port object to stop.
        @type port: L{IListeningPort} provider
        """
        stopped = port.stopListening()
        self.assertNotIn(port, self.reactor.getReaders())
        # An unfortunate implementation detail
        self.reactor.advance(0)
        self.assertIsNone(self.successResultOf(stopped))

    def test_stopListeningStopsReading(self):
        """
        L{TuntapPort.stopListening} returns a L{Deferred} which fires after the
        port has been removed from the reactor's reader list by passing it to
        the reactor's C{removeReader} method.
        """
        self.port.startListening()
        fileno = self.port.fileno()
        self._stopPort(self.port)

        self.assertNotIn(fileno, self.system._openFiles)

    def test_stopListeningUnsetsConnected(self):
        """
        After the L{Deferred} returned by L{TuntapPort.stopListening} fires,
        the C{connected} attribute of the port object is set to C{False}.
        """
        self.port.startListening()
        self._stopPort(self.port)
        self.assertFalse(self.port.connected)

    def test_stopListeningStopsProtocol(self):
        """
        L{TuntapPort.stopListening} calls C{doStop} on the protocol the port
        was initialized with.
        """
        self.port.startListening()
        self._stopPort(self.port)
        self.assertIsNone(self.protocol.transport)

    def test_stopListeningWhenStopped(self):
        """
        L{TuntapPort.stopListening} returns a L{Deferred} which succeeds
        immediately if it is called when the port is not listening.
        """
        stopped = self.port.stopListening()
        self.assertIsNone(self.successResultOf(stopped))

    def test_multipleStopListening(self):
        """
        It is safe and a no-op to call L{TuntapPort.stopListening} more than
        once with no intervening L{TuntapPort.startListening} call.
        """
        self.port.startListening()
        self.port.stopListening()
        second = self.port.stopListening()
        self.reactor.advance(0)
        self.assertIsNone(self.successResultOf(second))

    def test_loseConnection(self):
        """
        L{TuntapPort.loseConnection} stops the port and is deprecated.
        """
        self.port.startListening()

        self.port.loseConnection()
        # An unfortunate implementation detail
        self.reactor.advance(0)

        self.assertFalse(self.port.connected)
        warnings = self.flushWarnings([self.test_loseConnection])
        self.assertEqual(DeprecationWarning, warnings[0]["category"])
        self.assertEqual(
            "twisted.pair.tuntap.TuntapPort.loseConnection was deprecated "
            "in Twisted 14.0.0; please use twisted.pair.tuntap.TuntapPort."
            "stopListening instead",
            warnings[0]["message"],
        )
        self.assertEqual(1, len(warnings))

    def _stopsReadingTest(self, style):
        """
        Test that L{TuntapPort.doRead} has no side-effects under a certain
        exception condition.

        @param style: An exception instance to arrange for the (python wrapper
            around the) underlying platform I{read} call to fail with.

        @raise C{self.failureException}: If there are any observable
            side-effects.
        """
        self.port.startListening()
        tunnel = self.system.getTunnel(self.port)
        tunnel.nonBlockingExceptionStyle = style
        self.port.doRead()
        self.assertEqual([], self.protocol.received)

    def test_eagainStopsReading(self):
        """
        Once L{TuntapPort.doRead} encounters an I{EAGAIN} errno from a C{read}
        call, it returns.
        """
        self._stopsReadingTest(Tunnel.EAGAIN_STYLE)

    def test_ewouldblockStopsReading(self):
        """
        Once L{TuntapPort.doRead} encounters an I{EWOULDBLOCK} errno from a
        C{read} call, it returns.
        """
        self._stopsReadingTest(Tunnel.EWOULDBLOCK_STYLE)

    def test_eintrblockStopsReading(self):
        """
        Once L{TuntapPort.doRead} encounters an I{EINTR} errno from a C{read}
        call, it returns.
        """
        self._stopsReadingTest(Tunnel.EINTR_STYLE)

    def test_unhandledReadError(self):
        """
        If L{Tuntap.doRead} encounters any exception other than one explicitly
        handled by the code, the exception propagates to the caller.
        """

        class UnexpectedException(Exception):
            pass

        self.assertRaises(
            UnexpectedException, self._stopsReadingTest, UnexpectedException()
        )

    def test_unhandledEnvironmentReadError(self):
        """
        Just like C{test_unhandledReadError}, but for the case where the
        exception that is not explicitly handled happens to be of type
        C{EnvironmentError} (C{OSError} or C{IOError}).
        """
        self.assertRaises(
            IOError, self._stopsReadingTest, IOError(EPERM, "Operation not permitted")
        )

    def test_doReadSmallDatagram(self):
        """
        L{TuntapPort.doRead} reads a datagram of fewer than
        C{TuntapPort.maxPacketSize} from the port's file descriptor and passes
        it to its protocol's C{datagramReceived} method.
        """
        datagram = b"x" * (self.port.maxPacketSize - 1)
        self.port.startListening()
        tunnel = self.system.getTunnel(self.port)
        tunnel.readBuffer.append(datagram)
        self.port.doRead()
        self.assertEqual([datagram], self.protocol.received)

    def test_doReadLargeDatagram(self):
        """
        L{TuntapPort.doRead} reads the first part of a datagram of more than
        C{TuntapPort.maxPacketSize} from the port's file descriptor and passes
        the truncated data to its protocol's C{datagramReceived} method.
        """
        datagram = b"x" * self.port.maxPacketSize
        self.port.startListening()
        tunnel = self.system.getTunnel(self.port)
        tunnel.readBuffer.append(datagram + b"y")
        self.port.doRead()
        self.assertEqual([datagram], self.protocol.received)

    def test_doReadSeveralDatagrams(self):
        """
        L{TuntapPort.doRead} reads several datagrams, of up to
        C{TuntapPort.maxThroughput} bytes total, before returning.
        """
        values = cycle(iterbytes(b"abcdefghijklmnopqrstuvwxyz"))
        total = 0
        datagrams = []
        while total < self.port.maxThroughput:
            datagrams.append(next(values) * self.port.maxPacketSize)
            total += self.port.maxPacketSize

        self.port.startListening()
        tunnel = self.system.getTunnel(self.port)
        tunnel.readBuffer.extend(datagrams)
        tunnel.readBuffer.append(b"excessive datagram, not to be read")

        self.port.doRead()
        self.assertEqual(datagrams, self.protocol.received)

    def _datagramReceivedException(self):
        """
        Deliver some data to a L{TuntapPort} hooked up to an application
        protocol that raises an exception from its C{datagramReceived} method.

        @return: Whatever L{AttributeError} exceptions are logged.
        """
        self.port.startListening()
        self.system.getTunnel(self.port).readBuffer.append(b"ping")

        # Break the application logic
        self.protocol.received = None

        self.port.doRead()
        return self.flushLoggedErrors(AttributeError)

    def test_datagramReceivedException(self):
        """
        If the protocol's C{datagramReceived} method raises an exception, the
        exception is logged.
        """
        errors = self._datagramReceivedException()
        self.assertEqual(1, len(errors))

    def test_datagramReceivedExceptionIdentifiesProtocol(self):
        """
        The exception raised by C{datagramReceived} is logged with a message
        identifying the offending protocol.
        """
        messages = []
        addObserver(messages.append)
        self.addCleanup(removeObserver, messages.append)
        self._datagramReceivedException()
        error = next(m for m in messages if m["isError"])
        message = textFromEventDict(error)
        self.assertEqual(
            "Unhandled exception from %s.datagramReceived"
            % (fullyQualifiedName(self.protocol.__class__),),
            message.splitlines()[0],
        )

    def test_write(self):
        """
        L{TuntapPort.write} sends a datagram into the tunnel.
        """
        datagram = b"a b c d e f g"
        self.port.startListening()
        self.port.write(datagram)
        self.assertEqual(
            self.system.getTunnel(self.port).writeBuffer, deque([datagram])
        )

    def test_interruptedWrite(self):
        """
        If the platform write call is interrupted (causing the Python wrapper
        to raise C{IOError} with errno set to C{EINTR}), the write is re-tried.
        """
        self.port.startListening()
        tunnel = self.system.getTunnel(self.port)
        tunnel.pendingSignals.append(SIGINT)
        self.port.write(b"hello, world")
        self.assertEqual(deque([b"hello, world"]), tunnel.writeBuffer)

    def test_unhandledWriteError(self):
        """
        Any exception raised by the underlying write call, except for EINTR, is
        propagated to the caller.
        """
        self.port.startListening()
        tunnel = self.system.getTunnel(self.port)
        self.assertRaises(
            IOError, self.port.write, b"x" * tunnel.SEND_BUFFER_SIZE + b"y"
        )

    def test_writeSequence(self):
        """
        L{TuntapPort.writeSequence} sends a datagram into the tunnel by
        concatenating the byte strings in the list passed to it.
        """
        datagram = [b"a", b"b", b"c", b"d"]
        self.port.startListening()
        self.port.writeSequence(datagram)
        self.assertEqual(
            self.system.getTunnel(self.port).writeBuffer, deque([b"".join(datagram)])
        )

    def test_getHost(self):
        """
        L{TuntapPort.getHost} returns a L{TunnelAddress} including the tunnel's
        type and name.
        """
        self.port.startListening()
        address = self.port.getHost()
        self.assertEqual(
            TunnelAddress(
                self._tunnelTypeOnly(self.helper.TUNNEL_TYPE),
                self.system.getTunnel(self.port).name,
            ),
            address,
        )

    def test_listeningString(self):
        """
        The string representation of a L{TuntapPort} instance includes the
        tunnel type and interface and the protocol associated with the port.
        """
        self.port.startListening()
        self.assertRegex(str(self.port), fullyQualifiedName(self.protocol.__class__))

        expected = " listening on {}/{}>".format(
            self._tunnelTypeOnly(self.helper.TUNNEL_TYPE).name,
            self.system.getTunnel(self.port).name,
        )
        self.assertTrue(str(self.port).find(expected) != -1)

    def test_unlisteningString(self):
        """
        The string representation of a L{TuntapPort} instance includes the
        tunnel type and interface and the protocol associated with the port.
        """
        self.assertRegex(str(self.port), fullyQualifiedName(self.protocol.__class__))

        expected = " not listening on {}/{}>".format(
            self._tunnelTypeOnly(self.helper.TUNNEL_TYPE).name,
            self.name,
        )
        self.assertTrue(str(self.port).find(expected) != -1)

    def test_logPrefix(self):
        """
        L{TuntapPort.logPrefix} returns a string identifying the application
        protocol and the type of tunnel.
        """
        self.assertEqual(
            "%s (%s)"
            % (
                self.protocol.__class__.__name__,
                self._tunnelTypeOnly(self.helper.TUNNEL_TYPE).name,
            ),
            self.port.logPrefix(),
        )


class TunnelAddressTests(SynchronousTestCase):
    """
    Tests for L{TunnelAddress}.
    """

    def test_interfaces(self):
        """
        A L{TunnelAddress} instances provides L{IAddress}.
        """
        self.assertTrue(
            verifyObject(IAddress, TunnelAddress(TunnelFlags.IFF_TAP, "tap0"))
        )

    def test_indexing(self):
        """
        A L{TunnelAddress} instance can be indexed to retrieve either the byte
        string C{"TUNTAP"} or the name of the tunnel interface, while
        triggering a deprecation warning.
        """
        address = TunnelAddress(TunnelFlags.IFF_TAP, "tap0")
        self.assertEqual("TUNTAP", address[0])
        self.assertEqual("tap0", address[1])
        warnings = self.flushWarnings([self.test_indexing])
        message = (
            "TunnelAddress.__getitem__ is deprecated since Twisted 14.0.0  "
            "Use attributes instead."
        )
        self.assertEqual(DeprecationWarning, warnings[0]["category"])
        self.assertEqual(message, warnings[0]["message"])
        self.assertEqual(DeprecationWarning, warnings[1]["category"])
        self.assertEqual(message, warnings[1]["message"])
        self.assertEqual(2, len(warnings))

    def test_repr(self):
        """
        The string representation of a L{TunnelAddress} instance includes the
        class name and the values of the C{type} and C{name} attributes.
        """
        self.assertRegex(
            repr(TunnelAddress(TunnelFlags.IFF_TUN, name=b"device")),
            "TunnelAddress type=IFF_TUN name=b'device'>",
        )


class TunnelAddressEqualityTests(SynchronousTestCase):
    """
    Tests for the implementation of equality (C{==} and C{!=}) for
    L{TunnelAddress}.
    """

    def setUp(self):
        self.first = TunnelAddress(TunnelFlags.IFF_TUN, b"device")

        # Construct a different object representing IFF_TUN to make this a little
        # trickier.  Two FlagConstants from the same container and with the same
        # value do not compare equal to each other.
        #
        # The implementation will have to compare their values directly until
        # https://twistedmatrix.com/trac/ticket/6878 is resolved.
        self.second = TunnelAddress(
            TunnelFlags.IFF_TUN | TunnelFlags.IFF_TUN, b"device"
        )

        self.variedType = TunnelAddress(TunnelFlags.IFF_TAP, b"tap1")
        self.variedName = TunnelAddress(TunnelFlags.IFF_TUN, b"tun1")

    def test_selfComparesEqual(self):
        """
        A L{TunnelAddress} compares equal to itself.
        """
        self.assertTrue(self.first == self.first)

    def test_selfNotComparesNotEqual(self):
        """
        A L{TunnelAddress} doesn't compare not equal to itself.
        """
        self.assertFalse(self.first != self.first)

    def test_sameAttributesComparesEqual(self):
        """
        Two L{TunnelAddress} instances with the same value for the C{type} and
        C{name} attributes compare equal to each other.
        """
        self.assertTrue(self.first == self.second)

    def test_sameAttributesNotComparesNotEqual(self):
        """
        Two L{TunnelAddress} instances with the same value for the C{type} and
        C{name} attributes don't compare not equal to each other.
        """
        self.assertFalse(self.first != self.second)

    def test_differentTypeComparesNotEqual(self):
        """
        Two L{TunnelAddress} instances that differ only by the value of their
        type don't compare equal to each other.
        """
        self.assertFalse(self.first == self.variedType)

    def test_differentTypeNotComparesEqual(self):
        """
        Two L{TunnelAddress} instances that differ only by the value of their
        type compare not equal to each other.
        """
        self.assertTrue(self.first != self.variedType)

    def test_differentNameComparesNotEqual(self):
        """
        Two L{TunnelAddress} instances that differ only by the value of their
        name don't compare equal to each other.
        """
        self.assertFalse(self.first == self.variedName)

    def test_differentNameNotComparesEqual(self):
        """
        Two L{TunnelAddress} instances that differ only by the value of their
        name compare not equal to each other.
        """
        self.assertTrue(self.first != self.variedName)

    def test_differentClassNotComparesEqual(self):
        """
        A L{TunnelAddress} doesn't compare equal to an instance of another
        class.
        """
        self.assertFalse(self.first == self)

    def test_differentClassComparesNotEqual(self):
        """
        A L{TunnelAddress} compares not equal to an instance of another class.
        """
        self.assertTrue(self.first != self)


@implementer(IRawPacketProtocol)
class IPRecordingProtocol(AbstractDatagramProtocol):
    """
    A protocol which merely records the datagrams delivered to it.
    """

    def startProtocol(self):
        self.received = []

    def datagramReceived(
        self, datagram, partial=False, dest=None, source=None, protocol=None
    ):
        self.received.append(datagram)

    def addProto(self, num, proto):
        # IRawPacketProtocol.addProto
        pass


class TunTests(TunnelTestsMixin, SynchronousTestCase):
    """
    Tests for L{TuntapPort} when used to open a Linux I{tun} tunnel.
    """

    factory = Factory()
    # Type is wrong. See: https://twistedmatrix.com/trac/ticket/10008#ticket
    factory.protocol = IPRecordingProtocol  # type: ignore[assignment]
    helper = TunHelper(None, None)


class EthernetRecordingProtocol(EthernetProtocol):
    """
    A protocol which merely records the datagrams delivered to it.
    """

    def startProtocol(self):
        self.received = []

    def datagramReceived(self, datagram, partial=False):
        self.received.append(datagram)


class TapTests(TunnelTestsMixin, SynchronousTestCase):
    """
    Tests for L{TuntapPort} when used to open a Linux I{tap} tunnel.
    """

    factory = Factory()
    # Type is wrong. See: https://twistedmatrix.com/trac/ticket/10008#ticket
    factory.protocol = EthernetRecordingProtocol  # type: ignore[assignment]
    helper = TapHelper(None, None, pi=False)


class IOSystemTestsMixin:
    """
    Tests that apply to any L{_IInputOutputSystem} implementation.
    """

    def test_noSuchDevice(self):
        """
        L{_IInputOutputSystem.open} raises L{OSError} when called with a
        non-existent device path.
        """
        system = self.createSystem()
        self.assertRaises(
            OSError, system.open, b"/dev/there-is-no-such-device-ever", os.O_RDWR
        )


class MemoryIOSystemTests(
    IOSystemTestsMixin, SynchronousTestCase, FakeDeviceTestsMixin
):
    """
    General L{_IInputOutputSystem} tests applied to L{MemoryIOSystem}.
    """


class RealIOSystemTests(IOSystemTestsMixin, SynchronousTestCase, RealDeviceTestsMixin):
    """
    General L{_IInputOutputSystem} tests applied to L{_RealSystem}.
    """
