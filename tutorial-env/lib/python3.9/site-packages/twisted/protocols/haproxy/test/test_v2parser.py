# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.protocols.haproxy.V2Parser}.
"""

from twisted.internet import address
from twisted.trial import unittest
from .. import _v2parser
from .._exceptions import InvalidProxyHeader

V2_SIGNATURE = b"\x0D\x0A\x0D\x0A\x00\x0D\x0A\x51\x55\x49\x54\x0A"


def _makeHeaderIPv6(
    sig: bytes = V2_SIGNATURE,
    verCom: bytes = b"\x21",
    famProto: bytes = b"\x21",
    addrLength: bytes = b"\x00\x24",
    addrs: bytes = ((b"\x00" * 15) + b"\x01") * 2,
    ports: bytes = b"\x1F\x90\x22\xB8",
) -> bytes:
    """
    Construct a version 2 IPv6 header with custom bytes.

    @param sig: The protocol signature; defaults to valid L{V2_SIGNATURE}.
    @type sig: L{bytes}

    @param verCom: Protocol version and command.  Defaults to V2 PROXY.
    @type verCom: L{bytes}

    @param famProto: Address family and protocol.  Defaults to AF_INET6/STREAM.
    @type famProto: L{bytes}

    @param addrLength: Network-endian byte length of payload.  Defaults to
        description of default addrs/ports.
    @type addrLength: L{bytes}

    @param addrs: Address payload.  Defaults to C{::1} for source and
        destination.
    @type addrs: L{bytes}

    @param ports: Source and destination ports.  Defaults to 8080 for source
        8888 for destination.
    @type ports: L{bytes}

    @return: A packet with header, addresses, and ports.
    @rtype: L{bytes}
    """
    return sig + verCom + famProto + addrLength + addrs + ports


def _makeHeaderIPv4(
    sig: bytes = V2_SIGNATURE,
    verCom: bytes = b"\x21",
    famProto: bytes = b"\x11",
    addrLength: bytes = b"\x00\x0C",
    addrs: bytes = b"\x7F\x00\x00\x01\x7F\x00\x00\x01",
    ports: bytes = b"\x1F\x90\x22\xB8",
) -> bytes:
    """
    Construct a version 2 IPv4 header with custom bytes.

    @param sig: The protocol signature; defaults to valid L{V2_SIGNATURE}.
    @type sig: L{bytes}

    @param verCom: Protocol version and command.  Defaults to V2 PROXY.
    @type verCom: L{bytes}

    @param famProto: Address family and protocol.  Defaults to AF_INET/STREAM.
    @type famProto: L{bytes}

    @param addrLength: Network-endian byte length of payload.  Defaults to
        description of default addrs/ports.
    @type addrLength: L{bytes}

    @param addrs: Address payload.  Defaults to 127.0.0.1 for source and
        destination.
    @type addrs: L{bytes}

    @param ports: Source and destination ports.  Defaults to 8080 for source
        8888 for destination.
    @type ports: L{bytes}

    @return: A packet with header, addresses, and ports.
    @rtype: L{bytes}
    """
    return sig + verCom + famProto + addrLength + addrs + ports


def _makeHeaderUnix(
    sig: bytes = V2_SIGNATURE,
    verCom: bytes = b"\x21",
    famProto: bytes = b"\x31",
    addrLength: bytes = b"\x00\xD8",
    addrs: bytes = (
        b"\x2F\x68\x6F\x6D\x65\x2F\x74\x65\x73\x74\x73\x2F"
        b"\x6D\x79\x73\x6F\x63\x6B\x65\x74\x73\x2F\x73\x6F"
        b"\x63\x6B" + (b"\x00" * 82)
    )
    * 2,
) -> bytes:
    """
    Construct a version 2 IPv4 header with custom bytes.

    @param sig: The protocol signature; defaults to valid L{V2_SIGNATURE}.
    @type sig: L{bytes}

    @param verCom: Protocol version and command.  Defaults to V2 PROXY.
    @type verCom: L{bytes}

    @param famProto: Address family and protocol.  Defaults to AF_UNIX/STREAM.
    @type famProto: L{bytes}

    @param addrLength: Network-endian byte length of payload.  Defaults to 108
        bytes for 2 null terminated paths.
    @type addrLength: L{bytes}

    @param addrs: Address payload.  Defaults to C{/home/tests/mysockets/sock}
        for source and destination paths.
    @type addrs: L{bytes}

    @return: A packet with header, addresses, and8 ports.
    @rtype: L{bytes}
    """
    return sig + verCom + famProto + addrLength + addrs


class V2ParserTests(unittest.TestCase):
    """
    Test L{twisted.protocols.haproxy.V2Parser} behaviour.
    """

    def test_happyPathIPv4(self) -> None:
        """
        Test if a well formed IPv4 header is parsed without error.
        """
        header = _makeHeaderIPv4()
        self.assertTrue(_v2parser.V2Parser.parse(header))

    def test_happyPathIPv6(self) -> None:
        """
        Test if a well formed IPv6 header is parsed without error.
        """
        header = _makeHeaderIPv6()
        self.assertTrue(_v2parser.V2Parser.parse(header))

    def test_happyPathUnix(self) -> None:
        """
        Test if a well formed UNIX header is parsed without error.
        """
        header = _makeHeaderUnix()
        self.assertTrue(_v2parser.V2Parser.parse(header))

    def test_invalidSignature(self) -> None:
        """
        Test if an invalid signature block raises InvalidProxyError.
        """
        header = _makeHeaderIPv4(sig=b"\x00" * 12)
        self.assertRaises(
            InvalidProxyHeader,
            _v2parser.V2Parser.parse,
            header,
        )

    def test_invalidVersion(self) -> None:
        """
        Test if an invalid version raises InvalidProxyError.
        """
        header = _makeHeaderIPv4(verCom=b"\x11")
        self.assertRaises(
            InvalidProxyHeader,
            _v2parser.V2Parser.parse,
            header,
        )

    def test_invalidCommand(self) -> None:
        """
        Test if an invalid command raises InvalidProxyError.
        """
        header = _makeHeaderIPv4(verCom=b"\x23")
        self.assertRaises(
            InvalidProxyHeader,
            _v2parser.V2Parser.parse,
            header,
        )

    def test_invalidFamily(self) -> None:
        """
        Test if an invalid family raises InvalidProxyError.
        """
        header = _makeHeaderIPv4(famProto=b"\x40")
        self.assertRaises(
            InvalidProxyHeader,
            _v2parser.V2Parser.parse,
            header,
        )

    def test_invalidProto(self) -> None:
        """
        Test if an invalid protocol raises InvalidProxyError.
        """
        header = _makeHeaderIPv4(famProto=b"\x24")
        self.assertRaises(
            InvalidProxyHeader,
            _v2parser.V2Parser.parse,
            header,
        )

    def test_localCommandIpv4(self) -> None:
        """
        Test that local does not return endpoint data for IPv4 connections.
        """
        header = _makeHeaderIPv4(verCom=b"\x20")
        info = _v2parser.V2Parser.parse(header)
        self.assertFalse(info.source)
        self.assertFalse(info.destination)

    def test_localCommandIpv6(self) -> None:
        """
        Test that local does not return endpoint data for IPv6 connections.
        """
        header = _makeHeaderIPv6(verCom=b"\x20")
        info = _v2parser.V2Parser.parse(header)
        self.assertFalse(info.source)
        self.assertFalse(info.destination)

    def test_localCommandUnix(self) -> None:
        """
        Test that local does not return endpoint data for UNIX connections.
        """
        header = _makeHeaderUnix(verCom=b"\x20")
        info = _v2parser.V2Parser.parse(header)
        self.assertFalse(info.source)
        self.assertFalse(info.destination)

    def test_proxyCommandIpv4(self) -> None:
        """
        Test that proxy returns endpoint data for IPv4 connections.
        """
        header = _makeHeaderIPv4(verCom=b"\x21")
        info = _v2parser.V2Parser.parse(header)
        self.assertTrue(info.source)
        self.assertIsInstance(info.source, address.IPv4Address)
        self.assertTrue(info.destination)
        self.assertIsInstance(info.destination, address.IPv4Address)

    def test_proxyCommandIpv6(self) -> None:
        """
        Test that proxy returns endpoint data for IPv6 connections.
        """
        header = _makeHeaderIPv6(verCom=b"\x21")
        info = _v2parser.V2Parser.parse(header)
        self.assertTrue(info.source)
        self.assertIsInstance(info.source, address.IPv6Address)
        self.assertTrue(info.destination)
        self.assertIsInstance(info.destination, address.IPv6Address)

    def test_proxyCommandUnix(self) -> None:
        """
        Test that proxy returns endpoint data for UNIX connections.
        """
        header = _makeHeaderUnix(verCom=b"\x21")
        info = _v2parser.V2Parser.parse(header)
        self.assertTrue(info.source)
        self.assertIsInstance(info.source, address.UNIXAddress)
        self.assertTrue(info.destination)
        self.assertIsInstance(info.destination, address.UNIXAddress)

    def test_unspecFamilyIpv4(self) -> None:
        """
        Test that UNSPEC does not return endpoint data for IPv4 connections.
        """
        header = _makeHeaderIPv4(famProto=b"\x01")
        info = _v2parser.V2Parser.parse(header)
        self.assertFalse(info.source)
        self.assertFalse(info.destination)

    def test_unspecFamilyIpv6(self) -> None:
        """
        Test that UNSPEC does not return endpoint data for IPv6 connections.
        """
        header = _makeHeaderIPv6(famProto=b"\x01")
        info = _v2parser.V2Parser.parse(header)
        self.assertFalse(info.source)
        self.assertFalse(info.destination)

    def test_unspecFamilyUnix(self) -> None:
        """
        Test that UNSPEC does not return endpoint data for UNIX connections.
        """
        header = _makeHeaderUnix(famProto=b"\x01")
        info = _v2parser.V2Parser.parse(header)
        self.assertFalse(info.source)
        self.assertFalse(info.destination)

    def test_unspecProtoIpv4(self) -> None:
        """
        Test that UNSPEC does not return endpoint data for IPv4 connections.
        """
        header = _makeHeaderIPv4(famProto=b"\x10")
        info = _v2parser.V2Parser.parse(header)
        self.assertFalse(info.source)
        self.assertFalse(info.destination)

    def test_unspecProtoIpv6(self) -> None:
        """
        Test that UNSPEC does not return endpoint data for IPv6 connections.
        """
        header = _makeHeaderIPv6(famProto=b"\x20")
        info = _v2parser.V2Parser.parse(header)
        self.assertFalse(info.source)
        self.assertFalse(info.destination)

    def test_unspecProtoUnix(self) -> None:
        """
        Test that UNSPEC does not return endpoint data for UNIX connections.
        """
        header = _makeHeaderUnix(famProto=b"\x30")
        info = _v2parser.V2Parser.parse(header)
        self.assertFalse(info.source)
        self.assertFalse(info.destination)

    def test_overflowIpv4(self) -> None:
        """
        Test that overflow bits are preserved during feed parsing for IPv4.
        """
        testValue = b"TEST DATA\r\n\r\nTEST DATA"
        header = _makeHeaderIPv4() + testValue
        parser = _v2parser.V2Parser()
        info, overflow = parser.feed(header)
        self.assertTrue(info)
        self.assertEqual(overflow, testValue)

    def test_overflowIpv6(self) -> None:
        """
        Test that overflow bits are preserved during feed parsing for IPv6.
        """
        testValue = b"TEST DATA\r\n\r\nTEST DATA"
        header = _makeHeaderIPv6() + testValue
        parser = _v2parser.V2Parser()
        info, overflow = parser.feed(header)
        self.assertTrue(info)
        self.assertEqual(overflow, testValue)

    def test_overflowUnix(self) -> None:
        """
        Test that overflow bits are preserved during feed parsing for Unix.
        """
        testValue = b"TEST DATA\r\n\r\nTEST DATA"
        header = _makeHeaderUnix() + testValue
        parser = _v2parser.V2Parser()
        info, overflow = parser.feed(header)
        self.assertTrue(info)
        self.assertEqual(overflow, testValue)

    def test_segmentTooSmall(self) -> None:
        """
        Test that an initial payload of less than 16 bytes fails.
        """
        testValue = b"NEEDMOREDATA"
        parser = _v2parser.V2Parser()
        self.assertRaises(
            InvalidProxyHeader,
            parser.feed,
            testValue,
        )
