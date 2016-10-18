import time

from twisted.internet import defer
from twisted.internet.base import ThreadedResolver

from scrapy.utils.datatypes import LocalCache


# TODO: cache misses

class ExpiringCache(LocalCache):
    def __init__(self, limit=None, expiration=None):
        super(ExpiringCache, self).__init__(limit)
        self.expiration = expiration

    def __getitem__(self, key):
        setting_time, value = super(ExpiringCache, self).__getitem__(key)
        if self.expiration and setting_time + self.expiration < time.time():
            del self[key]
            raise KeyError("key expired")
        return value

    def __setitem__(self, key, value):
        super(ExpiringCache, self).__setitem__(key, (time.time(), value))


dnscache = ExpiringCache(10000)


class CachingThreadedResolver(ThreadedResolver):
    def __init__(self, reactor, cache_size, timeout, expiration=86400):
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
