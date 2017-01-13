# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.protocols.haproxy.V1Parser}.
"""

from twisted.trial import unittest
from twisted.internet import address

from .._exceptions import (
    InvalidProxyHeader, InvalidNetworkProtocol, MissingAddressData
)
from .. import _v1parser


class V1ParserTests(unittest.TestCase):
    """
    Test L{twisted.protocols.haproxy.V1Parser} behaviour.
    """

    def test_missingPROXYHeaderValue(self):
        """
        Test that an exception is raised when the PROXY header is missing.
        """
        self.assertRaises(
            InvalidProxyHeader,
            _v1parser.V1Parser.parse,
            b'NOTPROXY ',
        )


    def test_invalidNetworkProtocol(self):
        """
        Test that an exception is raised when the proto is not TCP or UNKNOWN.
        """
        self.assertRaises(
            InvalidNetworkProtocol,
            _v1parser.V1Parser.parse,
            b'PROXY WUTPROTO ',
        )


    def test_missingSourceData(self):
        """
        Test that an exception is raised when the proto has no source data.
        """
        self.assertRaises(
            MissingAddressData,
            _v1parser.V1Parser.parse,
            b'PROXY TCP4 ',
        )


    def test_missingDestData(self):
        """
        Test that an exception is raised when the proto has no destination.
        """
        self.assertRaises(
            MissingAddressData,
            _v1parser.V1Parser.parse,
            b'PROXY TCP4 127.0.0.1 8080 8888',
        )


    def test_fullParsingSuccess(self):
        """
        Test that parsing is successful for a PROXY header.
        """
        info = _v1parser.V1Parser.parse(
            b'PROXY TCP4 127.0.0.1 127.0.0.1 8080 8888',
        )
        self.assertIsInstance(info.source, address.IPv4Address)
        self.assertEqual(info.source.host, b'127.0.0.1')
        self.assertEqual(info.source.port, 8080)
        self.assertEqual(info.destination.host, b'127.0.0.1')
        self.assertEqual(info.destination.port, 8888)


    def test_fullParsingSuccess_IPv6(self):
        """
        Test that parsing is successful for an IPv6 PROXY header.
        """
        info = _v1parser.V1Parser.parse(
            b'PROXY TCP6 ::1 ::1 8080 8888',
        )
        self.assertIsInstance(info.source, address.IPv6Address)
        self.assertEqual(info.source.host, b'::1')
        self.assertEqual(info.source.port, 8080)
        self.assertEqual(info.destination.host, b'::1')
        self.assertEqual(info.destination.port, 8888)


    def test_fullParsingSuccess_UNKNOWN(self):
        """
        Test that parsing is successful for a UNKNOWN PROXY header.
        """
        info = _v1parser.V1Parser.parse(
            b'PROXY UNKNOWN anything could go here',
        )
        self.assertIsNone(info.source)
        self.assertIsNone(info.destination)


    def test_feedParsing(self):
        """
        Test that parsing happens when fed a complete line.
        """
        parser = _v1parser.V1Parser()
        info, remaining = parser.feed(b'PROXY TCP4 127.0.0.1 127.0.0.1 ')
        self.assertFalse(info)
        self.assertFalse(remaining)
        info, remaining = parser.feed(b'8080 8888')
        self.assertFalse(info)
        self.assertFalse(remaining)
        info, remaining = parser.feed(b'\r\n')
        self.assertFalse(remaining)
        self.assertIsInstance(info.source, address.IPv4Address)
        self.assertEqual(info.source.host, b'127.0.0.1')
        self.assertEqual(info.source.port, 8080)
        self.assertEqual(info.destination.host, b'127.0.0.1')
        self.assertEqual(info.destination.port, 8888)


    def test_feedParsingTooLong(self):
        """
        Test that parsing fails if no newline is found in 108 bytes.
        """
        parser = _v1parser.V1Parser()
        info, remaining = parser.feed(b'PROXY TCP4 127.0.0.1 127.0.0.1 ')
        self.assertFalse(info)
        self.assertFalse(remaining)
        info, remaining = parser.feed(b'8080 8888')
        self.assertFalse(info)
        self.assertFalse(remaining)
        self.assertRaises(
            InvalidProxyHeader,
            parser.feed,
            b' ' * 100,
        )


    def test_feedParsingOverflow(self):
        """
        Test that parsing leaves overflow bytes in the buffer.
        """
        parser = _v1parser.V1Parser()
        info, remaining = parser.feed(
            b'PROXY TCP4 127.0.0.1 127.0.0.1 8080 8888\r\nHTTP/1.1 GET /\r\n',
        )
        self.assertTrue(info)
        self.assertEqual(remaining, b'HTTP/1.1 GET /\r\n')
        self.assertFalse(parser.buffer)
