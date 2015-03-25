from twisted.internet import defer
from twisted.internet.base import ThreadedResolver

from scrapy.utils.datatypes import LocalCache

# TODO: cache misses

dnscache = LocalCache(10000)

class ScrapyResolver(ThreadedResolver):
    def __init__(self, reactor, settings):
        super(ScrapyResolver, self).__init__(reactor)
        self.caching_enabled = settings.getbool('DNSCACHE_ENABLED')
        if self.caching_enabled:
            dnscache.limit = settings.getint('DNS_CACHE_SIZE')

        threadpool = self.reactor.getThreadPool()
        threadpool.max = settings.getint('DNS_MAX_THREADS')
        self.timeout = tuple(settings.getlist('DNS_TIMEOUT'))

    def getHostByName(self, name, timeout=None):
        if self.caching_enabled and name in dnscache:
            return defer.succeed(dnscache[name])
        if not timeout:
            timeout = self.timeout
        d = super(ScrapyResolver, self).getHostByName(name, timeout)
        if self.caching_enabled:
            d.addCallback(self._cache_result, name)
        return d

    def _cache_result(self, result, name):
        dnscache[name] = result
        return result
