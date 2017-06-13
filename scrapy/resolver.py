from six import PY2, text_type

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
        if PY2 and isinstance(name, text_type):
            try:
                name = name.encode('idna')
            except UnicodeError:
                # we did our best, let it fail later if it has to.
                pass
        if name in dnscache:
            return defer.succeed(dnscache[name])
        # in Twisted<=16.6, getHostByName() is always called with
        # a default timeout of 60s (actually passed as (1, 3, 11, 45) tuple),
        # so the input argument above is simply overridden
        # to enforce Scrapy's DNS_TIMEOUT setting's value
        timeout = (self.timeout,)
        d = super(CachingThreadedResolver, self).getHostByName(name, timeout)
        d.addCallback(self._cache_result, name)
        return d

    def _cache_result(self, result, name):
        dnscache[name] = result
        return result
