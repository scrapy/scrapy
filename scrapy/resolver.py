from six import text_type

from twisted.internet import defer
from twisted.internet.base import ThreadedResolver

from scrapy.utils.datatypes import LocalCache

# TODO: cache misses

dnscache = LocalCache(10000)

class CachingThreadedResolver(ThreadedResolver):
    def __init__(self, reactor, cache_size, timeout):
        super(CachingThreadedResolver, self).__init__(reactor)
        dnscache.limit = cache_size
        self.timeout = timeout

    def getHostByName(self, name, timeout=None):
        if isinstance(name, text_type):
            try:
                safe_name = name.encode('idna')
            except UnicodeError:
                # we did our best, let it fail later.
                safe_name = name
        else:
            safe_name = name
        if safe_name in dnscache:
            return defer.succeed(dnscache[safe_name])
        # in Twisted<=16.6, getHostByName() is always called with
        # a default timeout of 60s (actually passed as (1, 3, 11, 45) tuple),
        # so the input argument above is simply overridden
        # to enforce Scrapy's DNS_TIMEOUT setting's value
        timeout = (self.timeout,)
        d = super(CachingThreadedResolver, self).getHostByName(safe_name, timeout)
        d.addCallback(self._cache_result, safe_name)
        return d

    def _cache_result(self, result, name):
        dnscache[name] = result
        return result
