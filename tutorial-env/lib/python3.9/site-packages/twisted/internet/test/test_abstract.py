# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.abstract}, a collection of APIs for implementing
reactors.
"""


from twisted.internet.abstract import isIPv6Address
from twisted.trial.unittest import SynchronousTestCase


class IPv6AddressTests(SynchronousTestCase):
    """
    Tests for L{isIPv6Address}, a function for determining if a particular
    string is an IPv6 address literal.
    """

    def test_empty(self):
        """
        The empty string is not an IPv6 address literal.
        """
        self.assertFalse(isIPv6Address(""))

    def test_colon(self):
        """
        A single C{":"} is not an IPv6 address literal.
        """
        self.assertFalse(isIPv6Address(":"))

    def test_loopback(self):
        """
        C{"::1"} is the IPv6 loopback address literal.
        """
        self.assertTrue(isIPv6Address("::1"))

    def test_scopeID(self):
        """
        An otherwise valid IPv6 address literal may also include a C{"%"}
        followed by an arbitrary scope identifier.
        """
        self.assertTrue(isIPv6Address("fe80::1%eth0"))
        self.assertTrue(isIPv6Address("fe80::2%1"))
        self.assertTrue(isIPv6Address("fe80::3%en2"))

    def test_invalidWithScopeID(self):
        """
        An otherwise invalid IPv6 address literal is still invalid with a
        trailing scope identifier.
        """
        self.assertFalse(isIPv6Address("%eth0"))
        self.assertFalse(isIPv6Address(":%eth0"))
        self.assertFalse(isIPv6Address("hello%eth0"))

    def test_unicodeAndBytes(self):
        """
        L{isIPv6Address} evaluates ASCII-encoded bytes as well as text.
        """
        self.assertTrue(isIPv6Address(b"fe80::2%1"))
        self.assertTrue(isIPv6Address("fe80::2%1"))
        self.assertFalse(isIPv6Address("\u4321"))
        self.assertFalse(isIPv6Address("hello%eth0"))
        self.assertFalse(isIPv6Address(b"hello%eth0"))
