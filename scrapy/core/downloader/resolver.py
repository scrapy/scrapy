"""DNS resolver with cache to use with Twisted reactors"""

from twisted.internet import defer
from twisted.internet.base import ThreadedResolver

from scrapy.core import signals
from scrapy.xlib.pydispatch import dispatcher

class CachingThreadedResolver(ThreadedResolver):

    def __init__(self, reactor):
        ThreadedResolver.__init__(self, reactor)
        self._cache = {}
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

    def getHostByName(self, name, timeout = (1, 3, 11, 45)):
        if name in self._cache:
            return defer.succeed(self._cache[name])
        dfd = ThreadedResolver.getHostByName(self, name, timeout)
        dfd.addCallback(self._cache_result, name)
        return dfd

    def _cache_result(self, result, name):
        self._cache[name] = result
        return result

    def domain_closed(self, spider):
        for domain in [spider.domain_name] + spider.extra_domain_names:
            self._cache.pop(domain, None)
