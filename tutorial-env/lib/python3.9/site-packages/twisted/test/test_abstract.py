# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for generic file descriptor based reactor support code.
"""


from socket import AF_IPX

from twisted.internet.abstract import isIPAddress
from twisted.trial.unittest import TestCase


class AddressTests(TestCase):
    """
    Tests for address-related functionality.
    """

    def test_decimalDotted(self):
        """
        L{isIPAddress} should return C{True} for any decimal dotted
        representation of an IPv4 address.
        """
        self.assertTrue(isIPAddress("0.1.2.3"))
        self.assertTrue(isIPAddress("252.253.254.255"))

    def test_shortDecimalDotted(self):
        """
        L{isIPAddress} should return C{False} for a dotted decimal
        representation with fewer or more than four octets.
        """
        self.assertFalse(isIPAddress("0"))
        self.assertFalse(isIPAddress("0.1"))
        self.assertFalse(isIPAddress("0.1.2"))
        self.assertFalse(isIPAddress("0.1.2.3.4"))

    def test_invalidLetters(self):
        """
        L{isIPAddress} should return C{False} for any non-decimal dotted
        representation including letters.
        """
        self.assertFalse(isIPAddress("a.2.3.4"))
        self.assertFalse(isIPAddress("1.b.3.4"))

    def test_invalidPunctuation(self):
        """
        L{isIPAddress} should return C{False} for a string containing
        strange punctuation.
        """
        self.assertFalse(isIPAddress(","))
        self.assertFalse(isIPAddress("1,2"))
        self.assertFalse(isIPAddress("1,2,3"))
        self.assertFalse(isIPAddress("1.,.3,4"))

    def test_emptyString(self):
        """
        L{isIPAddress} should return C{False} for the empty string.
        """
        self.assertFalse(isIPAddress(""))

    def test_invalidNegative(self):
        """
        L{isIPAddress} should return C{False} for negative decimal values.
        """
        self.assertFalse(isIPAddress("-1"))
        self.assertFalse(isIPAddress("1.-2"))
        self.assertFalse(isIPAddress("1.2.-3"))
        self.assertFalse(isIPAddress("1.2.-3.4"))

    def test_invalidPositive(self):
        """
        L{isIPAddress} should return C{False} for a string containing
        positive decimal values greater than 255.
        """
        self.assertFalse(isIPAddress("256.0.0.0"))
        self.assertFalse(isIPAddress("0.256.0.0"))
        self.assertFalse(isIPAddress("0.0.256.0"))
        self.assertFalse(isIPAddress("0.0.0.256"))
        self.assertFalse(isIPAddress("256.256.256.256"))

    def test_unicodeAndBytes(self):
        """
        L{isIPAddress} evaluates ASCII-encoded bytes as well as text.
        """
        self.assertFalse(isIPAddress(b"256.0.0.0"))
        self.assertFalse(isIPAddress("256.0.0.0"))
        self.assertTrue(isIPAddress(b"252.253.254.255"))
        self.assertTrue(isIPAddress("252.253.254.255"))

    def test_nonIPAddressFamily(self):
        """
        All address families other than C{AF_INET} and C{AF_INET6} result in a
        L{ValueError} being raised.
        """
        self.assertRaises(ValueError, isIPAddress, b"anything", AF_IPX)

    def test_nonASCII(self):
        """
        All IP addresses must be encodable as ASCII; non-ASCII should result in
        a L{False} result.
        """
        self.assertFalse(isIPAddress(b"\xff.notascii"))
        self.assertFalse(isIPAddress("\u4321.notascii"))
