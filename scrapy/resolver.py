from twisted.internet import defer
from twisted.internet.base import ThreadedResolver

from scrapy.utils.datatypes import ExpiringCache


# TODO: cache misses

dnscache = ExpiringCache(10000)


class CachingThreadedResolver(ThreadedResolver):
    def __init__(self, reactor, cache_size, timeout, expiration=None):
        super(CachingThreadedResolver, self).__init__(reactor)
        dnscache.limit = cache_size
        self.timeout = timeout
        dnscache.expiration = expiration

    def getHostByName(self, name, timeout=None):
        if name in dnscache:
            return defer.succeed(dnscache[name])
        if not timeout:
            timeout = self.timeout
        d = super(CachingThreadedResolver, self).getHostByName(name, timeout)
        d.addCallback(self._cache_result, name)
        return d

    def _cache_result(self, result, name):
        dnscache[name] = result
        return result
