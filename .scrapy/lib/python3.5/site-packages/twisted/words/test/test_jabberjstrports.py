# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.words.protocols.jabber.jstrports}.
"""

from __future__ import absolute_import, division

from twisted.trial import unittest

from twisted.words.protocols.jabber import jstrports
from twisted.application.internet import TCPClient


class JabberStrPortsPlaceHolderTests(unittest.TestCase):
    """
    Tests for L{jstrports}
    """

    def test_parse(self):
        """
        L{jstrports.parse} accepts an endpoint description string and returns a
        tuple and dict of parsed endpoint arguments.
        """
        expected = ('TCP', ('DOMAIN', 65535, 'Factory'), {})
        got = jstrports.parse("tcp:DOMAIN:65535", "Factory")
        self.assertEqual(expected, got)


    def test_client(self):
        """
        L{jstrports.client} returns a L{TCPClient} service.
        """
        got = jstrports.client("tcp:DOMAIN:65535", "Factory")
        self.assertIsInstance(got, TCPClient)
