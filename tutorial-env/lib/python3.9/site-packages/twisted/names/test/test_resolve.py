# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.names.resolve}.
"""

from twisted.names.error import DomainError
from twisted.names.resolve import ResolverChain
from twisted.trial.unittest import TestCase


class ResolverChainTests(TestCase):
    """
    Tests for L{twisted.names.resolve.ResolverChain}
    """

    def test_emptyResolversList(self):
        """
        L{ResolverChain._lookup} returns a L{DomainError} failure if
        its C{resolvers} list is empty.
        """
        r = ResolverChain([])
        d = r.lookupAddress("www.example.com")
        f = self.failureResultOf(d)
        self.assertIs(f.trap(DomainError), DomainError)

    def test_emptyResolversListLookupAllRecords(self):
        """
        L{ResolverChain.lookupAllRecords} returns a L{DomainError}
        failure if its C{resolvers} list is empty.
        """
        r = ResolverChain([])
        d = r.lookupAllRecords("www.example.com")
        f = self.failureResultOf(d)
        self.assertIs(f.trap(DomainError), DomainError)
