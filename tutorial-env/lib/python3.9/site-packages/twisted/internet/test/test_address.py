# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


import os
import socket
from unittest import skipIf

from twisted.internet.address import (
    HostnameAddress,
    IPv4Address,
    IPv6Address,
    UNIXAddress,
)
from twisted.python.compat import nativeString
from twisted.python.runtime import platform
from twisted.trial.unittest import SynchronousTestCase, TestCase

symlinkSkip = not platform._supportsSymlinks()

try:
    socket.AF_UNIX
except AttributeError:
    unixSkip = True
else:
    unixSkip = False


class AddressTestCaseMixin:
    def test_addressComparison(self):
        """
        Two different address instances, sharing the same properties are
        considered equal by C{==} and not considered not equal by C{!=}.

        Note: When applied via UNIXAddress class, this uses the same
        filename for both objects being compared.
        """
        self.assertTrue(self.buildAddress() == self.buildAddress())
        self.assertFalse(self.buildAddress() != self.buildAddress())

    def test_hash(self):
        """
        C{__hash__} can be used to get a hash of an address, allowing
        addresses to be used as keys in dictionaries, for instance.
        """
        addr = self.buildAddress()
        d = {addr: True}
        self.assertTrue(d[self.buildAddress()])

    def test_differentNamesComparison(self):
        """
        Check that comparison operators work correctly on address objects
        when a different name is passed in
        """
        self.assertFalse(self.buildAddress() == self.buildDifferentAddress())
        self.assertFalse(self.buildDifferentAddress() == self.buildAddress())

        self.assertTrue(self.buildAddress() != self.buildDifferentAddress())
        self.assertTrue(self.buildDifferentAddress() != self.buildAddress())

    def assertDeprecations(self, testMethod, message):
        """
        Assert that the a DeprecationWarning with the given message was
        emitted against the given method.
        """
        warnings = self.flushWarnings([testMethod])
        self.assertEqual(warnings[0]["category"], DeprecationWarning)
        self.assertEqual(warnings[0]["message"], message)
        self.assertEqual(len(warnings), 1)


class IPv4AddressTestCaseMixin(AddressTestCaseMixin):
    addressArgSpec = (("type", "%s"), ("host", "%r"), ("port", "%d"))


class HostnameAddressTests(TestCase, AddressTestCaseMixin):
    """
    Test case for L{HostnameAddress}.
    """

    addressArgSpec = (("hostname", "%s"), ("port", "%d"))

    def buildAddress(self):
        """
        Create an arbitrary new L{HostnameAddress} instance.

        @return: A L{HostnameAddress} instance.
        """
        return HostnameAddress(b"example.com", 0)

    def buildDifferentAddress(self):
        """
        Like L{buildAddress}, but with a different hostname.

        @return: A L{HostnameAddress} instance.
        """
        return HostnameAddress(b"example.net", 0)


class IPv4AddressTCPTests(SynchronousTestCase, IPv4AddressTestCaseMixin):
    def buildAddress(self):
        """
        Create an arbitrary new L{IPv4Address} instance with a C{"TCP"}
        type.  A new instance is created for each call, but always for the
        same address.
        """
        return IPv4Address("TCP", "127.0.0.1", 0)

    def buildDifferentAddress(self):
        """
        Like L{buildAddress}, but with a different fixed address.
        """
        return IPv4Address("TCP", "127.0.0.2", 0)


class IPv4AddressUDPTests(SynchronousTestCase, IPv4AddressTestCaseMixin):
    def buildAddress(self):
        """
        Create an arbitrary new L{IPv4Address} instance with a C{"UDP"}
        type.  A new instance is created for each call, but always for the
        same address.
        """
        return IPv4Address("UDP", "127.0.0.1", 0)

    def buildDifferentAddress(self):
        """
        Like L{buildAddress}, but with a different fixed address.
        """
        return IPv4Address("UDP", "127.0.0.2", 0)


class IPv6AddressTests(SynchronousTestCase, AddressTestCaseMixin):
    addressArgSpec = (("type", "%s"), ("host", "%r"), ("port", "%d"))

    def buildAddress(self):
        """
        Create an arbitrary new L{IPv6Address} instance with a C{"TCP"}
        type.  A new instance is created for each call, but always for the
        same address.
        """
        return IPv6Address("TCP", "::1", 0)

    def buildDifferentAddress(self):
        """
        Like L{buildAddress}, but with a different fixed address.
        """
        return IPv6Address("TCP", "::2", 0)


@skipIf(unixSkip, "Platform doesn't support UNIX sockets.")
class UNIXAddressTests(SynchronousTestCase):
    addressArgSpec = (("name", "%r"),)

    def setUp(self):
        self._socketAddress = self.mktemp()
        self._otherAddress = self.mktemp()

    def buildAddress(self):
        """
        Create an arbitrary new L{UNIXAddress} instance.  A new instance is
        created for each call, but always for the same address.
        """
        return UNIXAddress(self._socketAddress)

    def buildDifferentAddress(self):
        """
        Like L{buildAddress}, but with a different fixed address.
        """
        return UNIXAddress(self._otherAddress)

    def test_repr(self):
        """
        The repr of L{UNIXAddress} returns with the filename that the
        L{UNIXAddress} is for.
        """
        self.assertEqual(
            repr(self.buildAddress()),
            "UNIXAddress('%s')" % (nativeString(self._socketAddress)),
        )

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_comparisonOfLinkedFiles(self):
        """
        UNIXAddress objects compare as equal if they link to the same file.
        """
        linkName = self.mktemp()
        with open(self._socketAddress, "w") as self.fd:
            os.symlink(os.path.abspath(self._socketAddress), linkName)
            self.assertEqual(UNIXAddress(self._socketAddress), UNIXAddress(linkName))
            self.assertEqual(UNIXAddress(linkName), UNIXAddress(self._socketAddress))

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_hashOfLinkedFiles(self):
        """
        UNIXAddress Objects that compare as equal have the same hash value.
        """
        linkName = self.mktemp()
        with open(self._socketAddress, "w") as self.fd:
            os.symlink(os.path.abspath(self._socketAddress), linkName)
            self.assertEqual(
                hash(UNIXAddress(self._socketAddress)), hash(UNIXAddress(linkName))
            )


@skipIf(unixSkip, "platform doesn't support UNIX sockets.")
class EmptyUNIXAddressTests(SynchronousTestCase, AddressTestCaseMixin):
    """
    Tests for L{UNIXAddress} operations involving a L{None} address.
    """

    addressArgSpec = (("name", "%r"),)

    def setUp(self):
        self._socketAddress = self.mktemp()

    def buildAddress(self):
        """
        Create an arbitrary new L{UNIXAddress} instance.  A new instance is
        created for each call, but always for the same address. This builds it
        with a fixed address of L{None}.
        """
        return UNIXAddress(None)

    def buildDifferentAddress(self):
        """
        Like L{buildAddress}, but with a random temporary directory.
        """
        return UNIXAddress(self._socketAddress)

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_comparisonOfLinkedFiles(self):
        """
        A UNIXAddress referring to a L{None} address does not
        compare equal to a UNIXAddress referring to a symlink.
        """
        linkName = self.mktemp()
        with open(self._socketAddress, "w") as self.fd:
            os.symlink(os.path.abspath(self._socketAddress), linkName)
            self.assertNotEqual(UNIXAddress(self._socketAddress), UNIXAddress(None))
            self.assertNotEqual(UNIXAddress(None), UNIXAddress(self._socketAddress))

    def test_emptyHash(self):
        """
        C{__hash__} can be used to get a hash of an address, even one referring
        to L{None} rather than a real path.
        """
        addr = self.buildAddress()
        d = {addr: True}
        self.assertTrue(d[self.buildAddress()])
