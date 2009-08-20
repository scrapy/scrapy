from collections import defaultdict

from twisted.internet import reactor, defer
from twisted.internet.base import ThreadedResolver

from scrapy.xlib.pydispatch import dispatcher
from scrapy.utils.httpobj import urlparse_cached
from scrapy.core import signals


class CachingResolver(object):
    """Scrapy extension to use a caching resolver, instead of default one"""

    def __init__(self):
        self.spider_hostnames = defaultdict(set)
        self.resolver = _CachingThreadedResolver(reactor)
        reactor.installResolver(self.resolver)
        dispatcher.connect(self.request_received, signals.request_received)
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

    def request_received(self, request, spider):
        url_hostname = urlparse_cached(request).hostname
        self.spider_hostnames[spider.domain_name].add(url_hostname)

    def domain_closed(self, spider):
        for hostname in self.spider_hostnames:
            self.resolver._cache.pop(hostname, None)


class _CachingThreadedResolver(ThreadedResolver):

    def __init__(self, *args, **kwargs):
        ThreadedResolver.__init__(self, *args, **kwargs)
        self._cache = {}

    def getHostByName(self, name, timeout = (1, 3, 11, 45)):
        if name in self._cache:
            return defer.succeed(self._cache[name])
        dfd = ThreadedResolver.getHostByName(self, name, timeout)
        dfd.addCallback(self._cache_result, name)
        return dfd

    def _cache_result(self, result, name):
        self._cache[name] = result
        return result
