# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{SSHTransportAddrress} in ssh/address.py
"""


from twisted.conch.ssh.address import SSHTransportAddress
from twisted.internet.address import IPv4Address
from twisted.internet.test.test_address import AddressTestCaseMixin
from twisted.trial import unittest


class SSHTransportAddressTests(unittest.TestCase, AddressTestCaseMixin):
    """
    L{twisted.conch.ssh.address.SSHTransportAddress} is what Conch transports
    use to represent the other side of the SSH connection.  This tests the
    basic functionality of that class (string representation, comparison, &c).
    """

    def _stringRepresentation(self, stringFunction):
        """
        The string representation of C{SSHTransportAddress} should be
        "SSHTransportAddress(<stringFunction on address>)".
        """
        addr = self.buildAddress()
        stringValue = stringFunction(addr)
        addressValue = stringFunction(addr.address)
        self.assertEqual(stringValue, "SSHTransportAddress(%s)" % addressValue)

    def buildAddress(self):
        """
        Create an arbitrary new C{SSHTransportAddress}.  A new instance is
        created for each call, but always for the same address.
        """
        return SSHTransportAddress(IPv4Address("TCP", "127.0.0.1", 22))

    def buildDifferentAddress(self):
        """
        Like C{buildAddress}, but with a different fixed address.
        """
        return SSHTransportAddress(IPv4Address("TCP", "127.0.0.2", 22))
