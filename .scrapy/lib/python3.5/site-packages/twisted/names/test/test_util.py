# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Utilities for Twisted.names tests.
"""

from __future__ import division, absolute_import

from random import randrange

from zope.interface import implementer
from zope.interface.verify import verifyClass

from twisted.internet.address import IPv4Address
from twisted.internet.defer import succeed
from twisted.internet.task import Clock
from twisted.internet.interfaces import IReactorUDP, IUDPTransport



@implementer(IUDPTransport)
class MemoryDatagramTransport(object):
    """
    This L{IUDPTransport} implementation enforces the usual connection rules
    and captures sent traffic in a list for later inspection.

    @ivar _host: The host address to which this transport is bound.
    @ivar _protocol: The protocol connected to this transport.
    @ivar _sentPackets: A C{list} of two-tuples of the datagrams passed to
        C{write} and the addresses to which they are destined.

    @ivar _connectedTo: L{None} if this transport is unconnected, otherwise an
        address to which all traffic is supposedly sent.

    @ivar _maxPacketSize: An C{int} giving the maximum length of a datagram
        which will be successfully handled by C{write}.
    """
    def __init__(self, host, protocol, maxPacketSize):
        self._host = host
        self._protocol = protocol
        self._sentPackets = []
        self._connectedTo = None
        self._maxPacketSize = maxPacketSize


    def getHost(self):
        """
        Return the address which this transport is pretending to be bound
        to.
        """
        return IPv4Address('UDP', *self._host)


    def connect(self, host, port):
        """
        Connect this transport to the given address.
        """
        if self._connectedTo is not None:
            raise ValueError("Already connected")
        self._connectedTo = (host, port)


    def write(self, datagram, addr=None):
        """
        Send the given datagram.
        """
        if addr is None:
            addr = self._connectedTo
        if addr is None:
            raise ValueError("Need an address")
        if len(datagram) > self._maxPacketSize:
            raise ValueError("Packet too big")
        self._sentPackets.append((datagram, addr))


    def stopListening(self):
        """
        Shut down this transport.
        """
        self._protocol.stopProtocol()
        return succeed(None)


    def setBroadcastAllowed(self, enabled):
        """
        Dummy implementation to satisfy L{IUDPTransport}.
        """
        pass


    def getBroadcastAllowed(self):
        """
        Dummy implementation to satisfy L{IUDPTransport}.
        """
        pass


verifyClass(IUDPTransport, MemoryDatagramTransport)



@implementer(IReactorUDP)
class MemoryReactor(Clock):
    """
    An L{IReactorTime} and L{IReactorUDP} provider.

    Time is controlled deterministically via the base class, L{Clock}.  UDP is
    handled in-memory by connecting protocols to instances of
    L{MemoryDatagramTransport}.

    @ivar udpPorts: A C{dict} mapping port numbers to instances of
        L{MemoryDatagramTransport}.
    """
    def __init__(self):
        Clock.__init__(self)
        self.udpPorts = {}


    def listenUDP(self, port, protocol, interface='', maxPacketSize=8192):
        """
        Pretend to bind a UDP port and connect the given protocol to it.
        """
        if port == 0:
            while True:
                port = randrange(1, 2 ** 16)
                if port not in self.udpPorts:
                    break
        if port in self.udpPorts:
            raise ValueError("Address in use")
        transport = MemoryDatagramTransport(
            (interface, port), protocol, maxPacketSize)
        self.udpPorts[port] = transport
        protocol.makeConnection(transport)
        return transport

verifyClass(IReactorUDP, MemoryReactor)
