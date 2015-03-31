import socket
from twisted.python import failure
from twisted.internet import defer, threads
from twisted.internet.error import DNSLookupError
from twisted.internet.base import ThreadedResolver

from scrapy.utils.datatypes import LocalCache


IPV4_ONLY = 4
IPV6_ONLY = 6
IPV4_PREFERRED = 46
IPV6_PREFERRED = 64


class IPv6ThreadedResolver(ThreadedResolver):
    """ThreadedResolver calling socket.getaddrinfo for IPv6 capability.

    Uses a threadpool to perform name lookups without blocking the
    reactor thread. The underlying socket.getaddrinfo is a blocking call.
    """

    def __init__(self, reactor, protocol_preference=IPV4_PREFERRED):
        super(IPv6ThreadedResolver, self).__init__(reactor)
        self.protocol_preference = protocol_preference

        # protocol family sort order
        self.family_order = {
            socket.AF_INET :1 if self.protocol_preference == IPV4_PREFERRED else 10,
            socket.AF_INET6:2,
        }

    def _success(self, result, name):
        if self.protocol_preference == IPV4_PREFERRED \
                or self.protocol_preference == IPV6_PREFERRED:
            result = sorted(result,
                            key=lambda k:self.family_order.get(k[0]) or 99)
        # can only handle one result. pick the first one
        (family, socktype, proto, canonname, sockaddr) = result[0]
        if family == socket.AF_INET:
            (address, port) = sockaddr
            return address
        if family == socket.AF_INET6:
            (address, port, flow_info, scope_id) = sockaddr
            return address
        msg = "address %r not found (invalid AF type returned)" % (name,)
        err = DNSLookupError(msg)
        return failure.Failure(err)

    def getHostByName(self, name, timeout = (1, 3, 11, 45)):
        if timeout:
            timeoutDelay = sum(timeout)
        else:
            timeoutDelay = 60

        family = 0
        if self.protocol_preference == IPV4_ONLY:
            family = socket.AF_INET
        elif self.protocol_preference == IPV6_ONLY:
            family = socket.AF_INET6

        userDeferred = defer.Deferred()
        lookupDeferred = threads.deferToThreadPool(
            self.reactor, self.reactor.getThreadPool(),
            socket.getaddrinfo, name, None, family, 0, socket.IPPROTO_TCP, 0)
        cancelCall = self.reactor.callLater(
            timeoutDelay, self._cleanup, name, lookupDeferred)
        self._runningQueries[lookupDeferred] = (userDeferred, cancelCall)
        lookupDeferred.addBoth(self._checkTimeout, name, lookupDeferred)

        userDeferred.addCallback(self._success, name)
        return userDeferred


# TODO: cache misses

dnscache = LocalCache(10000)

class CachingThreadedResolver(IPv6ThreadedResolver):

    def __init__(self, reactor, cache_size, timeout, *a, **kw):
        super(CachingThreadedResolver, self).__init__(reactor, *a, **kw)
        dnscache.limit = cache_size
        self.timeout = timeout

    def getHostByName(self, name, timeout=None):
        if name in dnscache:
            return defer.succeed(dnscache[name])
        # in Twisted<=16.6, getHostByName() is always called with
        # a default timeout of 60s (actually passed as (1, 3, 11, 45) tuple),
        # so the input argument above is simply overridden
        # to enforce Scrapy's DNS_TIMEOUT setting's value
        timeout = (self.timeout,)
        d = super(CachingThreadedResolver, self).getHostByName(name, timeout)
        if dnscache.limit:
            d.addCallback(self._cache_result, name)
        return d

    def _cache_result(self, result, name):
        dnscache[name] = result
        return result
