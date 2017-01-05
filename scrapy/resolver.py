from functools import wraps
from socket import getaddrinfo
from zope.interface import implementer

from twisted.internet import defer
from twisted.internet.base import ThreadedResolver
from twisted.internet.interfaces import IHostnameResolver
from twisted.internet._resolver import GAIResolver

from scrapy.utils.datatypes import LocalCache

# TODO: cache misses

dnscache = LocalCache(10000)

class CachingThreadedResolver(ThreadedResolver):
    def __init__(self, reactor, cache_size, timeout):
        super(CachingThreadedResolver, self).__init__(reactor)
        dnscache.limit = cache_size
        self.timeout = timeout

    def getHostByName(self, name, timeout=None):
        if name in dnscache:
            return defer.succeed(dnscache[name])
        if not timeout:
            timeout = self.timeout
        d = super(CachingThreadedResolver, self).getHostByName(name)
        d.addCallback(self._cache_result, name)
        return d

    def _cache_result(self, result, name):
        dnscache[name] = result
        return result


# Borrowed from https://wiki.python.org/moin/PythonDecoratorLibrary#Alternate_memoize_as_nested_functions
# note that this decorator ignores **kwargs
def memoize(obj, cache):
    cache = cache

    @wraps(obj)
    def memoizer(*args, **kwargs):
        if args not in cache:
            cache[args] = obj(*args, **kwargs)
        return cache[args]
    return memoizer


@implementer(IHostnameResolver)
class CachingGAIResolver(GAIResolver):
    def __init__(self, reactor, getThreadPool=None, cache_size=0):
        dnscache.limit = cache_size
        super(CachingGAIResolver, self).__init__(reactor,
            getThreadPool=getThreadPool,
            getaddrinfo=memoize(getaddrinfo, dnscache) if cache_size
                else getaddrinfo)
