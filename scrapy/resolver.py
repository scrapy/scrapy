from twisted.internet import defer
from twisted.internet.base import ThreadedResolver
from twisted.internet.interfaces import (
    IHostnameResolver,
    IHostResolution,
    IResolutionReceiver,
    IResolverSimple,
)
from zope.interface.declarations import implementer, provider

from scrapy.utils.datatypes import LocalCache

# TODO: cache misses
dnscache = LocalCache(10000)


@implementer(IResolverSimple)
class CachingThreadedResolver(ThreadedResolver):
    """
    Default caching resolver. IPv4 only, supports setting a timeout value for DNS requests.
    """

    def __init__(self, reactor, cache_size, timeout):
        super().__init__(reactor)
        dnscache.limit = cache_size
        self.timeout = timeout

    @classmethod
    def from_crawler(cls, crawler, reactor):
        if crawler.settings.getbool("DNSCACHE_ENABLED"):
            cache_size = crawler.settings.getint("DNSCACHE_SIZE")
        else:
            cache_size = 0
        return cls(reactor, cache_size, crawler.settings.getfloat("DNS_TIMEOUT"))

    def install_on_reactor(self):
        self.reactor.installResolver(self)

    def getHostByName(self, name, timeout=None):
        if name in dnscache:
            return defer.succeed(dnscache[name])
        # in Twisted<=16.6, getHostByName() is always called with
        # a default timeout of 60s (actually passed as (1, 3, 11, 45) tuple),
        # so the input argument above is simply overridden
        # to enforce Scrapy's DNS_TIMEOUT setting's value
        timeout = (self.timeout,)
        d = super().getHostByName(name, timeout)
        if dnscache.limit:
            d.addCallback(self._cache_result, name)
        return d

    def _cache_result(self, result, name):
        dnscache[name] = result
        return result


@implementer(IHostResolution)
class HostResolution:
    def __init__(self, name):
        self.name = name

    def cancel(self):
        raise NotImplementedError()


@provider(IResolutionReceiver)
class _CachingResolutionReceiver:
    def __init__(self, resolutionReceiver, hostName):
        self.resolutionReceiver = resolutionReceiver
        self.hostName = hostName
        self.addresses = []

    def resolutionBegan(self, resolution):
        self.resolutionReceiver.resolutionBegan(resolution)
        self.resolution = resolution

    def addressResolved(self, address):
        self.resolutionReceiver.addressResolved(address)
        self.addresses.append(address)

    def resolutionComplete(self):
        self.resolutionReceiver.resolutionComplete()
        if self.addresses:
            dnscache[self.hostName] = self.addresses


@implementer(IHostnameResolver)
class CachingHostnameResolver:
    """
    Experimental caching resolver. Resolves IPv4 and IPv6 addresses,
    does not support setting a timeout value for DNS requests.
    """

    def __init__(self, reactor, cache_size):
        self.reactor = reactor
        self.original_resolver = reactor.nameResolver
        dnscache.limit = cache_size

    @classmethod
    def from_crawler(cls, crawler, reactor):
        if crawler.settings.getbool("DNSCACHE_ENABLED"):
            cache_size = crawler.settings.getint("DNSCACHE_SIZE")
        else:
            cache_size = 0
        return cls(reactor, cache_size)

    def install_on_reactor(self):
        self.reactor.installNameResolver(self)

    def resolveHostName(
        self,
        resolutionReceiver,
        hostName,
        portNumber=0,
        addressTypes=None,
        transportSemantics="TCP",
    ):
        try:
            addresses = dnscache[hostName]
        except KeyError:
            return self.original_resolver.resolveHostName(
                _CachingResolutionReceiver(resolutionReceiver, hostName),
                hostName,
                portNumber,
                addressTypes,
                transportSemantics,
            )
        else:
            resolutionReceiver.resolutionBegan(HostResolution(hostName))
            for addr in addresses:
                resolutionReceiver.addressResolved(addr)
            resolutionReceiver.resolutionComplete()
            return resolutionReceiver
