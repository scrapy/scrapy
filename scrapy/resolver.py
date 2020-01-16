from twisted.internet import defer
from twisted.internet.base import ThreadedResolver
from twisted.internet.interfaces import IHostnameResolver, IResolutionReceiver, IResolverSimple
from zope.interface.declarations import implementer, provider

from scrapy.utils.datatypes import LocalCache


# TODO: cache misses
dnscache = LocalCache(10000)


@implementer(IResolverSimple)
class CachingThreadedResolver(ThreadedResolver):
    """
    Default caching resolver. IPv4 only, supports setting a timeout value for DNS requests
    """

    @classmethod
    def install(cls, reactor, settings):
        if settings.getbool('DNSCACHE_ENABLED'):
            cache_size = settings.getint('DNSCACHE_SIZE')
        else:
            cache_size = 0
        resolver = cls(reactor, cache_size, settings.getfloat('DNS_TIMEOUT'))
        reactor.installResolver(resolver)

    def __init__(self, reactor, cache_size, timeout):
        super(CachingThreadedResolver, self).__init__(reactor)
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


@implementer(IHostnameResolver)
class CachingHostnameResolver:
    """
    Experimental caching resolver, supporting IPv4 and IPv6
    """

    @classmethod
    def install(cls, reactor, settings):
        if settings.getbool('DNSCACHE_ENABLED'):
            cache_size = settings.getint('DNSCACHE_SIZE')
        else:
            cache_size = 0
        resolver = cls(reactor.nameResolver, cache_size)
        reactor.installNameResolver(resolver)

    def __init__(self, resolver, cache_size):
        self.resolver = resolver
        dnscache.limit = cache_size

    def resolveHostName(self, resolutionReceiver, hostName, portNumber=0,
                        addressTypes=None, transportSemantics='TCP'):

        @provider(IResolutionReceiver)
        class CachingResolutionReceiver(resolutionReceiver):

            def resolutionBegan(self, resolution):
                super(CachingResolutionReceiver, self).resolutionBegan(resolution)
                self.resolution = resolution
                self.resolved = False

            def addressResolved(self, address):
                super(CachingResolutionReceiver, self).addressResolved(address)
                self.resolved = True

            def resolutionComplete(self):
                super(CachingResolutionReceiver, self).resolutionComplete()
                if self.resolved:
                    dnscache[hostName] = self.resolution

        try:
            result = dnscache[hostName]
        except KeyError:
            result = self.resolver.resolveHostName(
                CachingResolutionReceiver(),
                hostName,
                portNumber,
                addressTypes,
                transportSemantics
            )
        finally:
            return result
