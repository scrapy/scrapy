# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.protocols.haproxy.HAProxyProtocol}.
"""

from twisted.trial import unittest
from twisted.internet import address
from twisted.internet.protocol import Protocol, Factory
from twisted.test.proto_helpers import StringTransportWithDisconnection

from .._wrapper import HAProxyWrappingFactory



class StaticProtocol(Protocol):
    """
    Protocol stand-in that maintains test state.
    """

    def __init__(self):
        self.source = None
        self.destination = None
        self.data = b''
        self.disconnected = False


    def dataReceived(self, data):
        self.source = self.transport.getPeer()
        self.destination = self.transport.getHost()
        self.data += data



class HAProxyWrappingFactoryV1Tests(unittest.TestCase):
    """
    Test L{twisted.protocols.haproxy.HAProxyWrappingFactory} with v1 PROXY
    headers.
    """

    def test_invalidHeaderDisconnects(self):
        """
        Test if invalid headers result in connectionLost events.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.IPv4Address('TCP', b'127.1.1.1', 8080),
        )
        transport = StringTransportWithDisconnection()
        transport.protocol = proto
        proto.makeConnection(transport)
        proto.dataReceived(b'NOTPROXY anything can go here\r\n')
        self.assertFalse(transport.connected)


    def test_invalidPartialHeaderDisconnects(self):
        """
        Test if invalid headers result in connectionLost events.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.IPv4Address('TCP', b'127.1.1.1', 8080),
        )
        transport = StringTransportWithDisconnection()
        transport.protocol = proto
        proto.makeConnection(transport)
        proto.dataReceived(b'PROXY TCP4 1.1.1.1\r\n')
        proto.dataReceived(b'2.2.2.2 8080\r\n')
        self.assertFalse(transport.connected)


    def test_validIPv4HeaderResolves_getPeerHost(self):
        """
        Test if IPv4 headers result in the correct host and peer data.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.IPv4Address('TCP', b'127.0.0.1', 8080),
        )
        transport = StringTransportWithDisconnection()
        proto.makeConnection(transport)
        proto.dataReceived(b'PROXY TCP4 1.1.1.1 2.2.2.2 8080 8888\r\n')
        self.assertEqual(proto.getPeer().host, b'1.1.1.1')
        self.assertEqual(proto.getPeer().port, 8080)
        self.assertEqual(
            proto.wrappedProtocol.transport.getPeer().host,
            b'1.1.1.1',
        )
        self.assertEqual(
            proto.wrappedProtocol.transport.getPeer().port,
            8080,
        )
        self.assertEqual(proto.getHost().host, b'2.2.2.2')
        self.assertEqual(proto.getHost().port, 8888)
        self.assertEqual(
            proto.wrappedProtocol.transport.getHost().host,
            b'2.2.2.2',
        )
        self.assertEqual(
            proto.wrappedProtocol.transport.getHost().port,
            8888,
        )


    def test_validIPv6HeaderResolves_getPeerHost(self):
        """
        Test if IPv6 headers result in the correct host and peer data.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.IPv6Address('TCP', b'::1', 8080),
        )
        transport = StringTransportWithDisconnection()
        proto.makeConnection(transport)
        proto.dataReceived(b'PROXY TCP6 ::1 ::2 8080 8888\r\n')
        self.assertEqual(proto.getPeer().host, b'::1')
        self.assertEqual(proto.getPeer().port, 8080)
        self.assertEqual(
            proto.wrappedProtocol.transport.getPeer().host,
            b'::1',
        )
        self.assertEqual(
            proto.wrappedProtocol.transport.getPeer().port,
            8080,
        )
        self.assertEqual(proto.getHost().host, b'::2')
        self.assertEqual(proto.getHost().port, 8888)
        self.assertEqual(
            proto.wrappedProtocol.transport.getHost().host,
            b'::2',
        )
        self.assertEqual(
            proto.wrappedProtocol.transport.getHost().port,
            8888,
        )


    def test_overflowBytesSentToWrappedProtocol(self):
        """
        Test if non-header bytes are passed to the wrapped protocol.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.IPv6Address('TCP', b'::1', 8080),
        )
        transport = StringTransportWithDisconnection()
        proto.makeConnection(transport)
        proto.dataReceived(b'PROXY TCP6 ::1 ::2 8080 8888\r\nHTTP/1.1 / GET')
        self.assertEqual(proto.wrappedProtocol.data, b'HTTP/1.1 / GET')


    def test_overflowBytesSentToWrappedProtocolChunks(self):
        """
        Test if header streaming passes extra data appropriately.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.IPv6Address('TCP', b'::1', 8080),
        )
        transport = StringTransportWithDisconnection()
        proto.makeConnection(transport)
        proto.dataReceived(b'PROXY TCP6 ::1 ::2 ')
        proto.dataReceived(b'8080 8888\r\nHTTP/1.1 / GET')
        self.assertEqual(proto.wrappedProtocol.data, b'HTTP/1.1 / GET')


    def test_overflowBytesSentToWrappedProtocolAfter(self):
        """
        Test if wrapper writes all data to wrapped protocol after parsing.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.IPv6Address('TCP', b'::1', 8080),
        )
        transport = StringTransportWithDisconnection()
        proto.makeConnection(transport)
        proto.dataReceived(b'PROXY TCP6 ::1 ::2 ')
        proto.dataReceived(b'8080 8888\r\nHTTP/1.1 / GET')
        proto.dataReceived(b'\r\n\r\n')
        self.assertEqual(proto.wrappedProtocol.data, b'HTTP/1.1 / GET\r\n\r\n')



class HAProxyWrappingFactoryV2Tests(unittest.TestCase):
    """
    Test L{twisted.protocols.haproxy.HAProxyWrappingFactory} with v2 PROXY
    headers.
    """

    IPV4HEADER = (
        # V2 Signature
        b'\x0D\x0A\x0D\x0A\x00\x0D\x0A\x51\x55\x49\x54\x0A'
        # V2 PROXY command
        b'\x21'
        # AF_INET/STREAM
        b'\x11'
        # 12 bytes for 2 IPv4 addresses and two ports
        b'\x00\x0C'
        # 127.0.0.1 for source and destination
        b'\x7F\x00\x00\x01\x7F\x00\x00\x01'
        # 8080 for source 8888 for destination
        b'\x1F\x90\x22\xB8'
    )
    IPV6HEADER = (
        # V2 Signature
        b'\x0D\x0A\x0D\x0A\x00\x0D\x0A\x51\x55\x49\x54\x0A'
        # V2 PROXY command
        b'\x21'
        # AF_INET6/STREAM
        b'\x21'
        # 16 bytes for 2 IPv6 addresses and two ports
        b'\x00\x24'
        # ::1 for source and destination
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01'
        # 8080 for source 8888 for destination
        b'\x1F\x90\x22\xB8'
    )

    _SOCK_PATH = (
        b'\x2F\x68\x6F\x6D\x65\x2F\x74\x65\x73\x74\x73\x2F\x6D\x79\x73\x6F'
        b'\x63\x6B\x65\x74\x73\x2F\x73\x6F\x63\x6B' + (b'\x00' * 82)
    )
    UNIXHEADER = (
        # V2 Signature
        b'\x0D\x0A\x0D\x0A\x00\x0D\x0A\x51\x55\x49\x54\x0A'
        # V2 PROXY command
        b'\x21'
        # AF_UNIX/STREAM
        b'\x31'
        # 108 bytes for 2 null terminated paths
        b'\x00\xD8'
        # /home/tests/mysockets/sock for source and destination paths
    ) + _SOCK_PATH + _SOCK_PATH

    def test_invalidHeaderDisconnects(self):
        """
        Test if invalid headers result in connectionLost events.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.IPv6Address('TCP', b'::1', 8080),
        )
        transport = StringTransportWithDisconnection()
        transport.protocol = proto
        proto.makeConnection(transport)
        proto.dataReceived(b'\x00' + self.IPV4HEADER[1:])
        self.assertFalse(transport.connected)


    def test_validIPv4HeaderResolves_getPeerHost(self):
        """
        Test if IPv4 headers result in the correct host and peer data.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.IPv4Address('TCP', b'127.0.0.1', 8080),
        )
        transport = StringTransportWithDisconnection()
        proto.makeConnection(transport)
        proto.dataReceived(self.IPV4HEADER)
        self.assertEqual(proto.getPeer().host, b'127.0.0.1')
        self.assertEqual(proto.getPeer().port, 8080)
        self.assertEqual(
            proto.wrappedProtocol.transport.getPeer().host,
            b'127.0.0.1',
        )
        self.assertEqual(
            proto.wrappedProtocol.transport.getPeer().port,
            8080,
        )
        self.assertEqual(proto.getHost().host, b'127.0.0.1')
        self.assertEqual(proto.getHost().port, 8888)
        self.assertEqual(
            proto.wrappedProtocol.transport.getHost().host,
            b'127.0.0.1',
        )
        self.assertEqual(
            proto.wrappedProtocol.transport.getHost().port,
            8888,
        )


    def test_validIPv6HeaderResolves_getPeerHost(self):
        """
        Test if IPv6 headers result in the correct host and peer data.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.IPv4Address('TCP', b'::1', 8080),
        )
        transport = StringTransportWithDisconnection()
        proto.makeConnection(transport)
        proto.dataReceived(self.IPV6HEADER)
        self.assertEqual(proto.getPeer().host, b'0:0:0:0:0:0:0:1')
        self.assertEqual(proto.getPeer().port, 8080)
        self.assertEqual(
            proto.wrappedProtocol.transport.getPeer().host,
            b'0:0:0:0:0:0:0:1',
        )
        self.assertEqual(
            proto.wrappedProtocol.transport.getPeer().port,
            8080,
        )
        self.assertEqual(proto.getHost().host, b'0:0:0:0:0:0:0:1')
        self.assertEqual(proto.getHost().port, 8888)
        self.assertEqual(
            proto.wrappedProtocol.transport.getHost().host,
            b'0:0:0:0:0:0:0:1',
        )
        self.assertEqual(
            proto.wrappedProtocol.transport.getHost().port,
            8888,
        )


    def test_validUNIXHeaderResolves_getPeerHost(self):
        """
        Test if UNIX headers result in the correct host and peer data.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.UNIXAddress(b'/home/test/sockets/server.sock'),
        )
        transport = StringTransportWithDisconnection()
        proto.makeConnection(transport)
        proto.dataReceived(self.UNIXHEADER)
        self.assertEqual(proto.getPeer().name, b'/home/tests/mysockets/sock')
        self.assertEqual(
            proto.wrappedProtocol.transport.getPeer().name,
            b'/home/tests/mysockets/sock',
        )
        self.assertEqual(proto.getHost().name, b'/home/tests/mysockets/sock')
        self.assertEqual(
            proto.wrappedProtocol.transport.getHost().name,
            b'/home/tests/mysockets/sock',
        )


    def test_overflowBytesSentToWrappedProtocol(self):
        """
        Test if non-header bytes are passed to the wrapped protocol.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.IPv6Address('TCP', b'::1', 8080),
        )
        transport = StringTransportWithDisconnection()
        proto.makeConnection(transport)
        proto.dataReceived(self.IPV6HEADER + b'HTTP/1.1 / GET')
        self.assertEqual(proto.wrappedProtocol.data, b'HTTP/1.1 / GET')


    def test_overflowBytesSentToWrappedProtocolChunks(self):
        """
        Test if header streaming passes extra data appropriately.
        """
        factory = HAProxyWrappingFactory(Factory.forProtocol(StaticProtocol))
        proto = factory.buildProtocol(
            address.IPv6Address('TCP', b'::1', 8080),
        )
        transport = StringTransportWithDisconnection()
        proto.makeConnection(transport)
        proto.dataReceived(self.IPV6HEADER[:18])
        proto.dataReceived(self.IPV6HEADER[18:] + b'HTTP/1.1 / GET')
        self.assertEqual(proto.wrappedProtocol.data, b'HTTP/1.1 / GET')
