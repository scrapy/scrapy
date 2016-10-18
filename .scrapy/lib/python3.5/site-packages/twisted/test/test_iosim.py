# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.test.iosim}.
"""

from __future__ import absolute_import, division

from twisted.test.iosim import FakeTransport
from twisted.trial.unittest import TestCase


class FakeTransportTests(TestCase):
    """
    Tests for L{FakeTransport}.
    """

    def test_connectionSerial(self):
        """
        Each L{FakeTransport} receives a serial number that uniquely identifies
        it.
        """
        a = FakeTransport(object(), True)
        b = FakeTransport(object(), False)
        self.assertIsInstance(a.serial, int)
        self.assertIsInstance(b.serial, int)
        self.assertNotEqual(a.serial, b.serial)


    def test_writeSequence(self):
        """
        L{FakeTransport.writeSequence} will write a sequence of L{bytes} to the
        transport.
        """
        a = FakeTransport(object(), False)

        a.write(b"a")
        a.writeSequence([b"b", b"c", b"d"])

        self.assertEqual(b"".join(a.stream), b"abcd")
