import socket

from twisted.internet import defer
from twisted.internet.base import ThreadedResolver

from scrapy.utils.datatypes import LocalCache


dnscache = LocalCache(10000) # XXX: make size a setting?

def gethostbyname(hostname):
    if hostname not in dnscache:
        dnscache[hostname] = socket.gethostbyname(hostname)
    return dnscache[hostname]

class CachingThreadedResolver(ThreadedResolver):

    def getHostByName(self, name, timeout = (1, 3, 11, 45)):
        if name in dnscache:
            return defer.succeed(dnscache[name])
        d = ThreadedResolver.getHostByName(self, name, timeout)
        d.addCallback(self._cache_result, name)
        return d

    def _cache_result(self, result, name):
        dnscache[name] = result
        return result
