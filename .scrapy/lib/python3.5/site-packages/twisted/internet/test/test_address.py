# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import division, absolute_import

import re
import os
import socket

from twisted.trial import unittest
from twisted.internet.address import IPv4Address, UNIXAddress, IPv6Address
from twisted.internet.address import HostnameAddress
from twisted.python.compat import nativeString
from twisted.python.runtime import platform

if not platform._supportsSymlinks():
    symlinkSkip = "Platform does not support symlinks"
else:
    symlinkSkip = None

try:
    socket.AF_UNIX
except AttributeError:
    unixSkip = "Platform doesn't support UNIX sockets."
else:
    unixSkip = None


class AddressTestCaseMixin(object):
    def test_addressComparison(self):
        """
        Two different address instances, sharing the same properties are
        considered equal by C{==} and not considered not equal by C{!=}.

        Note: When applied via UNIXAddress class, this uses the same
        filename for both objects being compared.
        """
        self.assertTrue(self.buildAddress() == self.buildAddress())
        self.assertFalse(self.buildAddress() != self.buildAddress())


    def _stringRepresentation(self, stringFunction):
        """
        Verify that the string representation of an address object conforms to a
        simple pattern (the usual one for Python object reprs) and contains
        values which accurately reflect the attributes of the address.
        """
        addr = self.buildAddress()
        pattern = "".join([
           "^",
           "([^\(]+Address)", # class name,
           "\(",       # opening bracket,
           "([^)]+)",  # arguments,
           "\)",       # closing bracket,
           "$"
        ])
        stringValue = stringFunction(addr)
        m = re.match(pattern, stringValue)
        self.assertNotEqual(
            None, m,
            "%s does not match the standard __str__ pattern "
            "ClassName(arg1, arg2, etc)" % (stringValue,))
        self.assertEqual(addr.__class__.__name__, m.group(1))

        args = [x.strip() for x in m.group(2).split(",")]
        self.assertEqual(
            args,
            [argSpec[1] % (getattr(addr, argSpec[0]),)
             for argSpec in self.addressArgSpec])


    def test_str(self):
        """
        C{str} can be used to get a string representation of an address instance
        containing information about that address.
        """
        self._stringRepresentation(str)


    def test_repr(self):
        """
        C{repr} can be used to get a string representation of an address
        instance containing information about that address.
        """
        self._stringRepresentation(repr)


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
        self.assertEqual(warnings[0]['category'], DeprecationWarning)
        self.assertEqual(warnings[0]['message'], message)
        self.assertEqual(len(warnings), 1)



class IPv4AddressTestCaseMixin(AddressTestCaseMixin):
    addressArgSpec = (("type", "%s"), ("host", "%r"), ("port", "%d"))



class HostnameAddressTests(unittest.TestCase, AddressTestCaseMixin):
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



class IPv4AddressTCPTests(unittest.SynchronousTestCase,
                          IPv4AddressTestCaseMixin):
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


    def test_bwHackDeprecation(self):
        """
        If a value is passed for the C{_bwHack} parameter to L{IPv4Address},
        a deprecation warning is emitted.
        """
        # Construct this for warning side-effects, disregard the actual object.
        IPv4Address("TCP", "127.0.0.3", 0, _bwHack="TCP")

        message = (
            "twisted.internet.address.IPv4Address._bwHack is deprecated "
            "since Twisted 11.0")
        return self.assertDeprecations(self.test_bwHackDeprecation, message)



class IPv4AddressUDPTests(unittest.SynchronousTestCase,
                          IPv4AddressTestCaseMixin):
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


    def test_bwHackDeprecation(self):
        """
        If a value is passed for the C{_bwHack} parameter to L{IPv4Address},
        a deprecation warning is emitted.
        """
        # Construct this for warning side-effects, disregard the actual object.
        IPv4Address("UDP", "127.0.0.3", 0, _bwHack="UDP")

        message = (
            "twisted.internet.address.IPv4Address._bwHack is deprecated "
            "since Twisted 11.0")
        return self.assertDeprecations(self.test_bwHackDeprecation, message)



class IPv6AddressTests(unittest.SynchronousTestCase, AddressTestCaseMixin):
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



class UNIXAddressTests(unittest.SynchronousTestCase):
    skip = unixSkip
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
        self.assertEqual(repr(self.buildAddress()), "UNIXAddress('%s')" % (
            nativeString(self._socketAddress)))


    def test_comparisonOfLinkedFiles(self):
        """
        UNIXAddress objects compare as equal if they link to the same file.
        """
        linkName = self.mktemp()
        with open(self._socketAddress, 'w') as self.fd:
            os.symlink(os.path.abspath(self._socketAddress), linkName)
            self.assertEqual(UNIXAddress(self._socketAddress),
                             UNIXAddress(linkName))
            self.assertEqual(UNIXAddress(linkName),
                             UNIXAddress(self._socketAddress))
    if not unixSkip:
        test_comparisonOfLinkedFiles.skip = symlinkSkip


    def test_hashOfLinkedFiles(self):
        """
        UNIXAddress Objects that compare as equal have the same hash value.
        """
        linkName = self.mktemp()
        with open(self._socketAddress, 'w') as self.fd:
            os.symlink(os.path.abspath(self._socketAddress), linkName)
            self.assertEqual(hash(UNIXAddress(self._socketAddress)),
                            hash(UNIXAddress(linkName)))
    if not unixSkip:
        test_hashOfLinkedFiles.skip = symlinkSkip



class EmptyUNIXAddressTests(unittest.SynchronousTestCase,
                            AddressTestCaseMixin):
    """
    Tests for L{UNIXAddress} operations involving a L{None} address.
    """
    skip = unixSkip
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


    def test_comparisonOfLinkedFiles(self):
        """
        A UNIXAddress referring to a L{None} address does not compare equal to a
        UNIXAddress referring to a symlink.
        """
        linkName = self.mktemp()
        with open(self._socketAddress, 'w') as self.fd:
            os.symlink(os.path.abspath(self._socketAddress), linkName)
            self.assertNotEqual(UNIXAddress(self._socketAddress),
                                UNIXAddress(None))
            self.assertNotEqual(UNIXAddress(None),
                                UNIXAddress(self._socketAddress))
    if not unixSkip:
        test_comparisonOfLinkedFiles.skip = symlinkSkip


    def test_emptyHash(self):
        """
        C{__hash__} can be used to get a hash of an address, even one referring
        to L{None} rather than a real path.
        """
        addr = self.buildAddress()
        d = {addr: True}
        self.assertTrue(d[self.buildAddress()])


    def test_bwHackDeprecation(self):
        """
        If a value is passed for the C{_bwHack} parameter to L{UNIXAddress},
        a deprecation warning is emitted.
        """
        # Construct this for warning side-effects, disregard the actual object.
        UNIXAddress(None, _bwHack='UNIX')

        message = (
            "twisted.internet.address.UNIXAddress._bwHack is deprecated "
            "since Twisted 11.0")
        return self.assertDeprecations(self.test_bwHackDeprecation, message)
