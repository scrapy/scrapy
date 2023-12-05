# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for various parts of L{twisted.web}.
"""
from zope.interface import implementer, verify

from twisted.internet import defer, interfaces
from twisted.trial import unittest
from twisted.web import client


@implementer(interfaces.IStreamClientEndpoint)
class DummyEndPoint:

    """An endpoint that does not connect anywhere"""

    def __init__(self, someString):
        self.someString = someString

    def __repr__(self) -> str:
        return f"DummyEndPoint({self.someString})"

    def connect(self, factory):
        return defer.succeed(dict(factory=factory))


class HTTPConnectionPoolTests(unittest.TestCase):
    """
    Unit tests for L{client.HTTPConnectionPoolTest}.
    """

    def test_implements(self):
        """L{DummyEndPoint}s implements L{interfaces.IStreamClientEndpoint}"""
        ep = DummyEndPoint("something")
        verify.verifyObject(interfaces.IStreamClientEndpoint, ep)

    def test_repr(self):
        """connection L{repr()} includes endpoint's L{repr()}"""
        pool = client.HTTPConnectionPool(reactor=None)
        ep = DummyEndPoint("this_is_probably_unique")
        d = pool.getConnection("someplace", ep)
        result = self.successResultOf(d)
        representation = repr(result)
        self.assertIn(repr(ep), representation)
