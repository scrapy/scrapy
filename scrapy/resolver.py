from twisted.internet import defer
from twisted.internet.base import ThreadedResolver

from scrapy.utils.datatypes import LocalCache

# TODO: cache misses
# TODO: make cache size a setting

dnscache = LocalCache(10000)

class ScrapyResolver(ThreadedResolver):
    def __init__(self, reactor, settings):
        super(ScrapyResolver, self).__init__(reactor)
        self._tp_counter = 0
        self.caching_enabled = settings.getbool('DNSCACHE_ENABLED')

    def getHostByName(self, name, timeout = (1, 3, 11, 45)):
        if self.caching_enabled and name in dnscache:
            return defer.succeed(dnscache[name])
        if self._tp_counter == 20:
            threadpool = self.reactor.getThreadPool()
            threadpool.adjustPoolsize(5, 20)
            self._tp_counter = 0
        d = super(ScrapyResolver, self).getHostByName(name, timeout)
        if self.caching_enabled:
            d.addCallback(self._cache_result, name)
        self._tp_counter += 1
        return d

    def _cache_result(self, result, name):
        dnscache[name] = result
        return result
