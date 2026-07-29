"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, cast

import pytest
from twisted.internet.address import IPv6Address
from twisted.internet.interfaces import (
    IAddress,
    IHostnameResolver,
    IHostResolution,
    IReactorPluggableNameResolver,
    IResolutionReceiver,
)
from twisted.internet.protocol import Factory, Protocol
from twisted.web.client import URI, BrowserLikePolicyForHTTPS
from zope.interface import implementer

from scrapy import Spider
from scrapy.core.downloader.handlers.http11 import (
    HTTP11DownloadHandler,
    TunnelError,
    _tunnel_request_data,
    _TunnelingEndpoint,
)
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.resolver import HostResolution
from scrapy.utils.defer import maybe_deferred_to_future
from tests.utils import ipv6_loopback_available
from tests.utils.bases.download_handlers_http import (
    TestHttpBase,
    TestHttpProxyBase,
    TestHttpsBase,
    TestHttpsCustomCiphersBase,
    TestHttpsInvalidDNSIdBase,
    TestHttpsInvalidDNSPatternBase,
    TestHttpsTLSVersionBase,
    TestHttpsWrongHostnameBase,
    TestHttpWithCrawlerBase,
    TestMitmProxyBase,
    TestRealWebsiteBase,
    TestSimpleHttpsBase,
)
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

    from twisted.internet.base import ReactorBase
    from twisted.web.iweb import IPolicyForHTTPS

    from scrapy.core.downloader.handlers import DownloadHandlerProtocol


pytestmark = pytest.mark.requires_reactor  # HTTP11DownloadHandler requires a reactor


class HTTP11DownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return HTTP11DownloadHandler

    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return {
            "DOWNLOAD_HANDLERS": {
                "http": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
                "https": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
            }
        }


def test_not_configured_without_reactor() -> None:
    crawler = Crawler(Spider, {"TWISTED_REACTOR_ENABLED": False})
    with pytest.raises(NotConfigured):
        HTTP11DownloadHandler.from_crawler(crawler)


class TestHttp(HTTP11DownloadHandlerMixin, TestHttpBase):
    pass


class TestHttps(HTTP11DownloadHandlerMixin, TestHttpsBase):
    pass


class TestSimpleHttps(HTTP11DownloadHandlerMixin, TestSimpleHttpsBase):
    pass


class TestHttpsWrongHostname(HTTP11DownloadHandlerMixin, TestHttpsWrongHostnameBase):
    pass


class TestHttpsInvalidDNSId(HTTP11DownloadHandlerMixin, TestHttpsInvalidDNSIdBase):
    pass


class TestHttpsInvalidDNSPattern(
    HTTP11DownloadHandlerMixin, TestHttpsInvalidDNSPatternBase
):
    pass


class TestHttpsCustomCiphers(HTTP11DownloadHandlerMixin, TestHttpsCustomCiphersBase):
    pass


class TestHttpsTLSVersion(HTTP11DownloadHandlerMixin, TestHttpsTLSVersionBase):
    pass


class TestHttpWithCrawler(HTTP11DownloadHandlerMixin, TestHttpWithCrawlerBase):
    pass


class TestHttpsWithCrawler(TestHttpWithCrawler):
    is_secure = True


class TestHttpProxy(HTTP11DownloadHandlerMixin, TestHttpProxyBase):
    pass


class TestHttpsProxy(HTTP11DownloadHandlerMixin, TestHttpProxyBase):
    is_secure = True
    # not implemented
    handler_supports_tls_in_tls = False


@pytest.mark.requires_mitmproxy
class TestMitmProxy(HTTP11DownloadHandlerMixin, TestMitmProxyBase):
    # not implemented
    handler_supports_tls_in_tls = False


@pytest.mark.skipif(
    not ipv6_loopback_available(), reason="IPv6 loopback is not available"
)
class TestMitmProxyIPv6(TestMitmProxy):
    proxy_host = "::1"


@pytest.mark.parametrize(
    ("url", "expected_authority"),
    [
        # IPv6 literals stay bracketed in the CONNECT authority, even though
        # URI.host strips the brackets
        (b"https://[::1]:8443/x", b"[::1]:8443"),
        (b"https://[2001:db8::1]/x", b"[2001:db8::1]:443"),
        # IPv4-mapped IPv6 address
        (b"https://[::ffff:192.168.0.1]/x", b"[::ffff:192.168.0.1]:443"),
        # hostnames and IPv4 literals are left alone
        (b"https://example.com:8443/x", b"example.com:8443"),
        (b"https://127.0.0.1:8443/x", b"127.0.0.1:8443"),
    ],
)
def test_connect_authority(url: bytes, expected_authority: bytes) -> None:
    """The CONNECT request target and Host header must carry a valid authority
    for the tunneled destination, including brackets for IPv6 literals.
    """
    uri = URI.fromBytes(url)
    # _TunnelingAgent._getEndpoint passes URI.host through, i.e. bytes
    tunnel_req = _tunnel_request_data(
        _TunnelingEndpoint._format_host(uri.host), uri.port
    )
    assert tunnel_req == (
        b"CONNECT " + expected_authority + b" HTTP/1.1\r\n"
        b"Host: " + expected_authority + b"\r\n\r\n"
    )


@implementer(IHostnameResolver)
class _SentinelIPv6Resolver:
    """Resolves one sentinel hostname to ::1, delegating everything else.

    There is no portable hostname that resolves only to an IPv6 address, so the
    test that needs one provides it here.
    """

    hostname = "ipv6-only-proxy.invalid"

    def __init__(self, original: IHostnameResolver):
        self._original = original

    def resolveHostName(
        self,
        resolutionReceiver: IResolutionReceiver,
        hostName: str,
        portNumber: int = 0,
        addressTypes: Sequence[type[IAddress]] | None = None,
        transportSemantics: str = "TCP",
    ) -> IHostResolution:
        if hostName != self.hostname:
            return self._original.resolveHostName(
                resolutionReceiver,
                hostName,
                portNumber,
                addressTypes,
                transportSemantics,
            )
        resolutionReceiver.resolutionBegan(HostResolution(hostName))
        # Honor addressTypes, as a real resolver does: a caller that asks only
        # for IPv4 addresses gets no results for this name.
        if addressTypes is None or IPv6Address in addressTypes:
            resolutionReceiver.addressResolved(IPv6Address("TCP", "::1", portNumber))
        resolutionReceiver.resolutionComplete()
        return resolutionReceiver


@implementer(IHostnameResolver)
class _UnresolvingResolver:
    """Resolves nothing, and records what it was asked to resolve.

    Stands in for Scrapy's default resolver, which cannot resolve an IPv6
    literal: it only ever reports IPv4 addresses.
    """

    def __init__(self) -> None:
        self.names: list[str] = []

    def resolveHostName(
        self,
        resolutionReceiver: IResolutionReceiver,
        hostName: str,
        portNumber: int = 0,
        addressTypes: Sequence[type[IAddress]] | None = None,
        transportSemantics: str = "TCP",
    ) -> IHostResolution:
        self.names.append(hostName)
        resolution = HostResolution(hostName)
        resolutionReceiver.resolutionBegan(resolution)
        resolutionReceiver.resolutionComplete()
        return resolution


@implementer(IReactorPluggableNameResolver)
class _ReactorWithNameResolver:
    """The given reactor, but resolving names with the given resolver.

    ``HostnameEndpoint`` reads ``nameResolver`` off the reactor when it
    connects, so injecting one here keeps the test from having to install a
    resolver on the global reactor and restore it afterwards.
    """

    def __init__(self, reactor: object, nameResolver: IHostnameResolver):
        self._reactor = reactor
        self.nameResolver = nameResolver

    def installNameResolver(
        self, resolver: IHostnameResolver
    ) -> IHostnameResolver:  # pragma: no cover
        raise NotImplementedError

    def __getattr__(self, name: str) -> Any:
        return getattr(self._reactor, name)


class _FakeProxyProtocol(Protocol):
    """Answers any CONNECT request with a refusal, so no TLS is attempted."""

    def dataReceived(self, data: bytes) -> None:
        assert self.transport
        self.transport.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")


@pytest.fixture
def fake_proxy_port() -> Generator[int]:
    """The port of a CONNECT-answering server listening on ::1."""
    from twisted.internet import reactor

    listening_port = reactor.listenTCP(
        0, Factory.forProtocol(_FakeProxyProtocol), interface="::1"
    )
    try:
        yield listening_port.getHost().port
    finally:
        listening_port.stopListening()


@pytest.fixture
def ipv6_only_proxy(fake_proxy_port: int) -> tuple[ReactorBase, str, int]:
    """That server, reachable only by a name that resolves to ::1."""
    from twisted.internet import reactor

    resolving_reactor = _ReactorWithNameResolver(
        reactor, _SentinelIPv6Resolver(reactor.nameResolver)
    )
    return (
        cast("ReactorBase", resolving_reactor),
        _SentinelIPv6Resolver.hostname,
        fake_proxy_port,
    )


@pytest.mark.skipif(
    not ipv6_loopback_available(), reason="IPv6 loopback is not available"
)
@coroutine_test
async def test_tunnel_to_proxy_reachable_only_over_ipv6(
    ipv6_only_proxy: tuple[ReactorBase, str, int],
) -> None:
    """The CONNECT tunnel must reach a proxy whose name resolves only to IPv6.

    Getting as far as a TunnelError means the proxy was reached and answered; a
    connection error instead would mean the endpoint picked the wrong address
    family for the proxy.
    """
    reactor, proxy_host, proxy_port = ipv6_only_proxy
    endpoint = _TunnelingEndpoint(
        reactor=reactor,
        host="example.com",
        port=443,
        proxyConf=(proxy_host, proxy_port, None),
        contextFactory=cast("IPolicyForHTTPS", BrowserLikePolicyForHTTPS()),
        timeout=10,
    )
    with pytest.raises(TunnelError, match="Could not open CONNECT tunnel"):
        await maybe_deferred_to_future(endpoint.connect(Factory.forProtocol(Protocol)))


@pytest.mark.skipif(
    not ipv6_loopback_available(), reason="IPv6 loopback is not available"
)
@coroutine_test
async def test_tunnel_to_ipv6_literal_proxy(fake_proxy_port: int) -> None:
    """The CONNECT tunnel must reach a proxy given as an IPv6 address literal
    without resolving it, as the default resolver cannot resolve one.
    """
    from twisted.internet import reactor

    resolver = _UnresolvingResolver()
    endpoint = _TunnelingEndpoint(
        reactor=cast("ReactorBase", _ReactorWithNameResolver(reactor, resolver)),
        host="example.com",
        port=443,
        proxyConf=("::1", fake_proxy_port, None),
        contextFactory=cast("IPolicyForHTTPS", BrowserLikePolicyForHTTPS()),
        timeout=10,
    )
    with pytest.raises(TunnelError, match="Could not open CONNECT tunnel"):
        await maybe_deferred_to_future(endpoint.connect(Factory.forProtocol(Protocol)))
    assert not resolver.names


@pytest.mark.requires_internet
class TestRealWebsite(HTTP11DownloadHandlerMixin, TestRealWebsiteBase):
    @property
    def platform_cert_store_works(self) -> bool:
        return sys.platform != "win32"
