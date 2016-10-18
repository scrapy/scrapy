# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.names.cache}.
"""

from __future__ import division, absolute_import

import time

from zope.interface.verify import verifyClass

from twisted.trial import unittest

from twisted.names import dns, cache
from twisted.internet import task, interfaces


class CachingTests(unittest.TestCase):
    """
    Tests for L{cache.CacheResolver}.
    """

    def test_interface(self):
        """
        L{cache.CacheResolver} implements L{interfaces.IResolver}
        """
        verifyClass(interfaces.IResolver, cache.CacheResolver)


    def test_lookup(self):
        c = cache.CacheResolver({
            dns.Query(name=b'example.com', type=dns.MX, cls=dns.IN):
                (time.time(), ([], [], []))})
        return c.lookupMailExchange(b'example.com').addCallback(
            self.assertEqual, ([], [], []))


    def test_constructorExpires(self):
        """
        Cache entries passed into L{cache.CacheResolver.__init__} get
        cancelled just like entries added with cacheResult
        """
        r = ([dns.RRHeader(b"example.com", dns.A, dns.IN, 60,
                           dns.Record_A("127.0.0.1", 60))],
             [dns.RRHeader(b"example.com", dns.A, dns.IN, 50,
                           dns.Record_A("127.0.0.1", 50))],
             [dns.RRHeader(b"example.com", dns.A, dns.IN, 40,
                           dns.Record_A("127.0.0.1", 40))])

        clock = task.Clock()
        query = dns.Query(name=b"example.com", type=dns.A, cls=dns.IN)

        c = cache.CacheResolver({ query : (clock.seconds(), r)}, reactor=clock)

        # 40 seconds is enough to expire the entry because expiration is based
        # on the minimum TTL.
        clock.advance(40)

        self.assertNotIn(query, c.cache)

        return self.assertFailure(
            c.lookupAddress(b"example.com"), dns.DomainError)


    def test_normalLookup(self):
        """
        When a cache lookup finds a cached entry from 1 second ago, it is
        returned with a TTL of original TTL minus the elapsed 1 second.
        """
        r = ([dns.RRHeader(b"example.com", dns.A, dns.IN, 60,
                           dns.Record_A("127.0.0.1", 60))],
             [dns.RRHeader(b"example.com", dns.A, dns.IN, 50,
                           dns.Record_A("127.0.0.1", 50))],
             [dns.RRHeader(b"example.com", dns.A, dns.IN, 40,
                           dns.Record_A("127.0.0.1", 40))])

        clock = task.Clock()

        c = cache.CacheResolver(reactor=clock)
        c.cacheResult(dns.Query(name=b"example.com", type=dns.A, cls=dns.IN), r)

        clock.advance(1)

        def cbLookup(result):
            self.assertEqual(result[0][0].ttl, 59)
            self.assertEqual(result[1][0].ttl, 49)
            self.assertEqual(result[2][0].ttl, 39)
            self.assertEqual(result[0][0].name.name, b"example.com")

        return c.lookupAddress(b"example.com").addCallback(cbLookup)


    def test_cachedResultExpires(self):
        """
        Once the TTL has been exceeded, the result is removed from the cache.
        """
        r = ([dns.RRHeader(b"example.com", dns.A, dns.IN, 60,
                           dns.Record_A("127.0.0.1", 60))],
             [dns.RRHeader(b"example.com", dns.A, dns.IN, 50,
                           dns.Record_A("127.0.0.1", 50))],
             [dns.RRHeader(b"example.com", dns.A, dns.IN, 40,
                           dns.Record_A("127.0.0.1", 40))])

        clock = task.Clock()

        c = cache.CacheResolver(reactor=clock)
        query = dns.Query(name=b"example.com", type=dns.A, cls=dns.IN)
        c.cacheResult(query, r)

        clock.advance(40)

        self.assertNotIn(query, c.cache)

        return self.assertFailure(
            c.lookupAddress(b"example.com"), dns.DomainError)


    def test_expiredTTLLookup(self):
        """
        When the cache is queried exactly as the cached entry should expire but
        before it has actually been cleared, the cache does not return the
        expired entry.
        """
        r = ([dns.RRHeader(b"example.com", dns.A, dns.IN, 60,
                           dns.Record_A("127.0.0.1", 60))],
             [dns.RRHeader(b"example.com", dns.A, dns.IN, 50,
                           dns.Record_A("127.0.0.1", 50))],
             [dns.RRHeader(b"example.com", dns.A, dns.IN, 40,
                           dns.Record_A("127.0.0.1", 40))])

        clock = task.Clock()
        # Make sure timeouts never happen, so entries won't get cleared:
        clock.callLater = lambda *args, **kwargs: None

        c = cache.CacheResolver({
            dns.Query(name=b"example.com", type=dns.A, cls=dns.IN) :
                (clock.seconds(), r)}, reactor=clock)

        clock.advance(60.1)

        return self.assertFailure(
            c.lookupAddress(b"example.com"), dns.DomainError)
