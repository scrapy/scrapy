from twisted.internet import defer
from twisted.internet.base import ThreadedResolver

from scrapy.utils.datatypes import LocalCache

# TODO: cache misses

dnscache = LocalCache(10000)

class CachingThreadedResolver(ThreadedResolver):
    def __init__(self, reactor, settings):
        super(CachingThreadedResolver, self).__init__(reactor)
        self.caching_enabled = settings.getbool('DNSCACHE_ENABLED')
        if self.caching_enabled:
            dnscache.limit = settings.getint('DNSCACHE_SIZE')
        self.timeout = settings.getint('DNS_TIMEOUT')

    def getHostByName(self, name, timeout=None):
        if self.caching_enabled and name in dnscache:
            return defer.succeed(dnscache[name])
        if not timeout:
            timeout = self.timeout
        d = super(CachingThreadedResolver, self).getHostByName(name, timeout)
        if self.caching_enabled:
            d.addCallback(self._cache_result, name)
        return d

    def _cache_result(self, result, name):
        dnscache[name] = result
        return result
