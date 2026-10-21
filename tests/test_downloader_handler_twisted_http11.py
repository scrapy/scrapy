from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

import pytest
from twisted.internet.address import IPv6Address
from twisted.internet.defer import CancelledError
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet.error import ConnectingCancelledError, ConnectionClosed
from twisted.internet.interfaces import (
    IAddress,
    IHostnameResolver,
    IHostResolution,
    IReactorPluggableNameResolver,
    IResolutionReceiver,
)
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.testing import MemoryReactorClock, StringTransport
from twisted.python.failure import Failure
from twisted.web.client import URI, BrowserLikePolicyForHTTPS
from zope.interface import implementer

try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]

from scrapy import Request, Spider
from scrapy.core.downloader.contextfactory import _load_context_factory_from_settings
from scrapy.core.downloader.handlers._base_http import _auto_connection_limit
from scrapy.core.downloader.handlers.http11 import (
    HTTP11DownloadHandler,
    TunnelError,
    _ScrapyAgent,
    _tunnel_request_data,
    _TunnelEndpoint,
    _TunnelingAgent,
    _TunnelProtocol,
)
from scrapy.crawler import Crawler
from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    NotConfigured,
)
from scrapy.resolver import HostResolution
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests import NON_EXISTING_RESOLVABLE
from tests.mockserver.utils import _free_port
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
    from collections.abc import AsyncGenerator, Generator, Sequence

    from twisted.internet.base import ReactorBase
    from twisted.internet.interfaces import IProtocol, IStreamClientEndpoint
    from twisted.web.iweb import IPolicyForHTTPS

    from scrapy.core.downloader.handlers import DownloadHandlerProtocol
    from tests.utils.bases.download_handlers_http import HeaderNameCase


pytestmark = pytest.mark.requires_reactor  # HTTP11DownloadHandler requires a reactor


class HTTP11DownloadHandlerMixin:
    handler_supports_partial_response_on_timeout = True

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

    handler_supports_custom_content_length = False
    handler_request_header_name_case: HeaderNameCase = "canonical"
    handler_response_header_name_case: HeaderNameCase = "canonical"


def test_not_configured_without_reactor() -> None:
    crawler = Crawler(Spider, {"TWISTED_REACTOR_ENABLED": False})
    with pytest.raises(NotConfigured):
        build_from_crawler(HTTP11DownloadHandler, crawler)


def _tunnel_endpoint(reactor: MemoryReactorClock) -> _TunnelEndpoint:
    return _TunnelEndpoint(
        TCP4ClientEndpoint(reactor, "127.0.0.1", 8080),
        host=b"example.com",
        port=443,
        proxyHost="127.0.0.1",
        proxyPort=8080,
    )


@asynccontextmanager
async def _get_dh(
    settings_dict: dict[str, Any] | None = None,
) -> AsyncGenerator[HTTP11DownloadHandler]:
    crawler = get_crawler(DefaultSpider, settings_dict)
    crawler.spider = crawler._create_spider()
    dh = build_from_crawler(HTTP11DownloadHandler, crawler)
    try:
        yield dh
    finally:
        await dh.close()


@coroutine_test
async def test_connection_limit_auto() -> None:
    async with _get_dh({}) as dh:
        assert dh._pool._limit == _auto_connection_limit()


@coroutine_test
@pytest.mark.parametrize("limit", [0, 20])
async def test_connection_limit_explicit(limit: int) -> None:
    async with _get_dh({"CONCURRENT_CONNECTIONS_PER_HANDLER": limit}) as dh:
        assert dh._pool._limit == limit


@coroutine_test
async def test_connection_limit_below_concurrent_requests(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings_dict = {
        "CONCURRENT_CONNECTIONS_PER_HANDLER": 4,
        "CONCURRENT_REQUESTS": 8,
    }
    with caplog.at_level("WARNING"):
        async with _get_dh(settings_dict):
            pass
    assert "CONCURRENT_CONNECTIONS_PER_HANDLER (4)" in caplog.text


@pytest.mark.skipif(resource is None, reason="No file descriptor limit")
@coroutine_test
async def test_connection_limit_auto_without_file_descriptor_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    infinity = resource.RLIM_INFINITY
    monkeypatch.setattr(resource, "getrlimit", lambda _: (infinity, infinity))
    async with _get_dh({}) as dh:
        assert dh._pool._limit == 0


@coroutine_test
async def test_keepalive_timeout() -> None:
    async with _get_dh({"CONNECTION_KEEPALIVE_TIMEOUT": 5}) as dh:
        assert dh._pool.cachedConnectionTimeout == 5


@pytest.mark.parametrize(
    ("proxy_headers", "proxy_auth", "expected"),
    [
        (None, None, ()),
        ({"X-B": "2", "X-A": "1"}, None, (("X-A", "1"), ("X-B", "2"))),
        (None, "Basic Zm9v", (("Proxy-Authorization", "Basic Zm9v"),)),
        (
            {"X-A": "1"},
            "Basic Zm9v",
            (("Proxy-Authorization", "Basic Zm9v"), ("X-A", "1")),
        ),
        (
            {"Proxy-Authorization": "Custom foo"},
            "Basic Zm9v",
            (("Proxy-Authorization", "Custom foo"),),
        ),
    ],
    ids=[
        "no headers",
        "sorted headers",
        "auth header",
        "auth header and headers",
        "auth header overridden",
    ],
)
def test_tunnel_proxy_headers(
    proxy_headers: dict[str, str] | None,
    proxy_auth: str | None,
    expected: tuple[tuple[str, str], ...],
) -> None:
    meta: dict[str, Any] = {"proxy": "http://proxy.example:8080"}
    if proxy_headers is not None:
        meta["proxy_headers"] = proxy_headers
    request = Request(
        "https://example.com",
        meta=meta,
        headers={"Proxy-Authorization": proxy_auth} if proxy_auth else None,
    )
    crawler = get_crawler(Spider)
    agent = _ScrapyAgent(
        contextFactory=_load_context_factory_from_settings(crawler), crawler=crawler
    )
    tunneling_agent = agent._get_agent(request, 10)
    assert isinstance(tunneling_agent, _TunnelingAgent)
    assert tunneling_agent._proxyConf == ("proxy.example", 8080, expected, False)


def test_tunneling_cancelled_before_connected() -> None:
    """Cancelling a tunneled download before the connection to the proxy is
    established stops the connection attempt.

    A download cannot reach this scenario, because the connection timeout of
    the endpoint, which uses the same value as the download timeout, always
    fires earlier than the cancellation. See also
    ``test_download_with_proxy_stalled_connect``, which covers cancelling once
    the connection to the proxy is established.
    """
    reactor = MemoryReactorClock()
    results: list[IProtocol | Failure] = []
    d = _tunnel_endpoint(reactor).connect(Factory.forProtocol(Protocol))
    d.addBoth(results.append)

    d.cancel()

    assert reactor.connectors[0].stoppedConnecting
    assert isinstance(results[0], Failure)
    assert isinstance(results[0].value, ConnectingCancelledError)


def test_tunneling_cancelled_before_connect_response() -> None:
    """A CONNECT response received after cancelling the tunnel, but before the
    connection to the proxy is closed, is ignored."""
    reactor = MemoryReactorClock()
    results: list[IProtocol | Failure] = []
    d = _tunnel_endpoint(reactor).connect(Factory.forProtocol(Protocol))
    d.addBoth(results.append)
    factory = reactor.tcpClients[0][2]
    protocol = factory.buildProtocol(None)
    assert protocol is not None
    transport = StringTransport()
    protocol.makeConnection(transport)

    d.cancel()
    protocol.dataReceived(b"HTTP/1.1 200 OK\r\n\r\n")

    assert transport.disconnecting
    assert len(results) == 1
    assert isinstance(results[0], Failure)
    assert isinstance(results[0].value, CancelledError)


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


@pytest.mark.requires_mitmproxy
class TestMitmProxy(HTTP11DownloadHandlerMixin, TestMitmProxyBase):
    pass


@pytest.mark.skipif(
    not ipv6_loopback_available(), reason="IPv6 loopback is not available"
)
class TestMitmProxyIPv6(TestMitmProxy):
    proxy_host = "::1"


@pytest.mark.parametrize(
    ("url", "expected_authority"),
    [
        (b"https://[::1]:8443/x", b"[::1]:8443"),
        (b"https://[::ffff:192.168.0.1]/x", b"[::ffff:192.168.0.1]:443"),
        (b"https://example.com:8443/x", b"example.com:8443"),
        (b"https://127.0.0.1:8443/x", b"127.0.0.1:8443"),
    ],
)
def test_connect_authority(url: bytes, expected_authority: bytes) -> None:
    uri = URI.fromBytes(url)
    tunnel_req = _tunnel_request_data(_TunnelProtocol._format_host(uri.host), uri.port)
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


def _proxy_tunnel_endpoint(
    reactor: ReactorBase, proxy_host: str, proxy_port: int
) -> IStreamClientEndpoint:
    agent = _TunnelingAgent(
        reactor=reactor,
        proxyConf=(proxy_host, proxy_port, (), False),
        contextFactory=cast("IPolicyForHTTPS", BrowserLikePolicyForHTTPS()),
        connectTimeout=10,
    )
    return agent._getEndpoint(URI.fromBytes(b"https://example.com"))


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
    endpoint = _proxy_tunnel_endpoint(reactor, proxy_host, proxy_port)
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
    endpoint = _proxy_tunnel_endpoint(
        cast("ReactorBase", _ReactorWithNameResolver(reactor, resolver)),
        "::1",
        fake_proxy_port,
    )
    with pytest.raises(TunnelError, match="Could not open CONNECT tunnel"):
        await maybe_deferred_to_future(endpoint.connect(Factory.forProtocol(Protocol)))
    assert not resolver.names


@pytest.mark.requires_internet
class TestRealWebsite(HTTP11DownloadHandlerMixin, TestRealWebsiteBase):
    @property
    def platform_cert_store_works(self) -> bool:
        return sys.platform != "win32"


class _CannedConnectProxy(Protocol):
    """Answers any request with a canned response, or drops the connection when
    the response is ``None``."""

    factory: _CannedConnectProxyFactory

    def dataReceived(self, data: bytes) -> None:
        from twisted.internet import reactor

        assert self.transport
        response = self.factory.response
        if response is None:
            self.transport.loseConnection()
            return
        if not self.factory.split_at:
            self.transport.write(response)
            return
        self.transport.write(response[: self.factory.split_at])
        reactor.callLater(0.1, self.transport.write, response[self.factory.split_at :])


class _CannedConnectProxyFactory(Factory):
    protocol = _CannedConnectProxy  # type: ignore[assignment]

    def __init__(self, response: bytes | None, split_at: int = 0):
        self.response = response
        self.split_at = split_at


@asynccontextmanager
async def _canned_proxy(
    response: bytes | None, split_at: int = 0
) -> AsyncGenerator[str]:
    from twisted.internet import reactor

    port = reactor.listenTCP(
        0, _CannedConnectProxyFactory(response, split_at), interface="127.0.0.1"
    )
    try:
        yield f"http://127.0.0.1:{port.getHost().port}"
    finally:
        await maybe_deferred_to_future(port.stopListening())


class TestTunnelingErrors:
    @coroutine_test
    async def test_response_in_two_packets(self) -> None:
        """A CONNECT response split across packets is buffered until complete."""
        response = b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n"
        async with _canned_proxy(response, split_at=len(response) - 2) as proxy:
            request = Request("https://example.com", meta={"proxy": proxy})
            async with _get_dh() as dh:
                with pytest.raises(TunnelError, match="407"):
                    await dh.download_request(request)

    @coroutine_test
    async def test_unparsable_response(self) -> None:
        async with _canned_proxy(b"not an HTTP response\r\n\r\n") as proxy:
            request = Request("https://example.com", meta={"proxy": proxy})
            async with _get_dh() as dh:
                with pytest.raises(TunnelError, match="not an HTTP response"):
                    await dh.download_request(request)

    @coroutine_test
    async def test_proxy_closes_connection(self) -> None:
        """The proxy drops the connection instead of answering CONNECT."""
        async with _canned_proxy(None) as proxy:
            request = Request("https://example.com", meta={"proxy": proxy})
            async with _get_dh() as dh:
                with pytest.raises(ConnectionClosed):
                    await dh.download_request(request)

    @coroutine_test
    async def test_trailing_bytes(self) -> None:
        """Bytes right after a successful CONNECT response belong to the
        tunneled protocol, whose TLS handshake they corrupt."""
        response = b"HTTP/1.1 200 Connection established\r\n\r\ntrailing-bytes"
        async with _canned_proxy(response) as proxy:
            request = Request("https://example.com", meta={"proxy": proxy})
            async with _get_dh() as dh:
                with pytest.raises(DownloadFailedError):
                    await dh.download_request(request)

    @coroutine_test
    async def test_proxy_connection_refused(self) -> None:
        request = Request(
            "https://example.com", meta={"proxy": f"http://127.0.0.1:{_free_port()}"}
        )
        async with _get_dh() as dh:
            with pytest.raises(DownloadConnectionRefusedError):
                await dh.download_request(request)

    @coroutine_test
    async def test_proxy_without_port(self) -> None:
        if NON_EXISTING_RESOLVABLE:
            pytest.skip("Non-existing hosts are resolvable")
        request = Request(
            "https://example.com", meta={"proxy": "http://no-such-domain.nosuch"}
        )
        async with _get_dh() as dh:
            with pytest.raises(CannotResolveHostError):
                await dh.download_request(request)
