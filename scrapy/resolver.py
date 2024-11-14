from __future__ import annotations

from typing import TYPE_CHECKING, Any

from twisted.internet import defer
from twisted.internet.base import ReactorBase, ThreadedResolver
from twisted.internet.interfaces import (
    IAddress,
    IHostnameResolver,
    IHostResolution,
    IResolutionReceiver,
    IResolverSimple,
)
from zope.interface.declarations import implementer, provider

from scrapy.utils.datatypes import LocalCache

if TYPE_CHECKING:
    from collections.abc import Sequence

    from twisted.internet.defer import Deferred

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler

# TODO: cache misses
dnscache: LocalCache[str, Any] = LocalCache(10000)


@implementer(IResolverSimple)
class CachingThreadedResolver(ThreadedResolver):
    """
    Default caching resolver. IPv4 only, supports setting a timeout value for DNS requests.
    """

    def __init__(self, reactor: ReactorBase, cache_size: int, timeout: float):
        super().__init__(reactor)
        dnscache.limit = cache_size
        self.timeout = timeout

    @classmethod
    def from_crawler(cls, crawler: Crawler, reactor: ReactorBase) -> Self:
        if crawler.settings.getbool("DNSCACHE_ENABLED"):
            cache_size = crawler.settings.getint("DNSCACHE_SIZE")
        else:
            cache_size = 0
        return cls(reactor, cache_size, crawler.settings.getfloat("DNS_TIMEOUT"))

    def install_on_reactor(self) -> None:
        self.reactor.installResolver(self)

    def getHostByName(self, name: str, timeout: Sequence[int] = ()) -> Deferred[str]:
        if name in dnscache:
            return defer.succeed(dnscache[name])
        # in Twisted<=16.6, getHostByName() is always called with
        # a default timeout of 60s (actually passed as (1, 3, 11, 45) tuple),
        # so the input argument above is simply overridden
        # to enforce Scrapy's DNS_TIMEOUT setting's value
        # The timeout arg is typed as Sequence[int] but supports floats.
        timeout = (self.timeout,)  # type: ignore[assignment]
        d = super().getHostByName(name, timeout)
        if dnscache.limit:
            d.addCallback(self._cache_result, name)
        return d

    def _cache_result(self, result: Any, name: str) -> Any:
        dnscache[name] = result
        return result


@implementer(IHostResolution)
class HostResolution:
    def __init__(self, name: str):
        self.name: str = name

    def cancel(self) -> None:
        raise NotImplementedError()


@provider(IResolutionReceiver)
class _CachingResolutionReceiver:
    def __init__(self, resolutionReceiver: IResolutionReceiver, hostName: str):
        self.resolutionReceiver: IResolutionReceiver = resolutionReceiver
        self.hostName: str = hostName
        self.addresses: list[IAddress] = []

    def resolutionBegan(self, resolution: IHostResolution) -> None:
        self.resolutionReceiver.resolutionBegan(resolution)
        self.resolution = resolution

    def addressResolved(self, address: IAddress) -> None:
        self.resolutionReceiver.addressResolved(address)
        self.addresses.append(address)

    def resolutionComplete(self) -> None:
        self.resolutionReceiver.resolutionComplete()
        if self.addresses:
            dnscache[self.hostName] = self.addresses


@implementer(IHostnameResolver)
class CachingHostnameResolver:
    """
    Experimental caching resolver. Resolves IPv4 and IPv6 addresses,
    does not support setting a timeout value for DNS requests.
    """

    def __init__(self, reactor: ReactorBase, cache_size: int):
        self.reactor: ReactorBase = reactor
        self.original_resolver: IHostnameResolver = reactor.nameResolver
        dnscache.limit = cache_size

    @classmethod
    def from_crawler(cls, crawler: Crawler, reactor: ReactorBase) -> Self:
        if crawler.settings.getbool("DNSCACHE_ENABLED"):
            cache_size = crawler.settings.getint("DNSCACHE_SIZE")
        else:
            cache_size = 0
        return cls(reactor, cache_size)

    def install_on_reactor(self) -> None:
        self.reactor.installNameResolver(self)

    def resolveHostName(
        self,
        resolutionReceiver: IResolutionReceiver,
        hostName: str,
        portNumber: int = 0,
        addressTypes: Sequence[type[IAddress]] | None = None,
        transportSemantics: str = "TCP",
    ) -> IHostResolution:
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
        resolutionReceiver.resolutionBegan(HostResolution(hostName))
        for addr in addresses:
            resolutionReceiver.addressResolved(addr)
        resolutionReceiver.resolutionComplete()
        return resolutionReceiver
