"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import Mock

import pytest
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.testing import StringTransport
from twisted.web._newclient import Request as TxClientRequest
from twisted.web._newclient import RequestNotSent
from twisted.web.http_headers import Headers as TxHeaders

from scrapy import Request, Spider
from scrapy.core.downloader.handlers.http11 import (
    HTTP11DownloadHandler,
    TunnelError,
    _ScrapyHTTP11ClientProtocol,
    _TunnelingTCP4ClientEndpoint,
)
from scrapy.crawler import Crawler
from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadConnectionRefusedError,
    NotConfigured,
    ResponseHeadersTooLargeError,
)
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests import NON_EXISTING_RESOLVABLE
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
    from collections.abc import AsyncGenerator

    from twisted.python.failure import Failure

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
        build_from_crawler(HTTP11DownloadHandler, crawler)


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


@pytest.mark.requires_internet
class TestRealWebsite(HTTP11DownloadHandlerMixin, TestRealWebsiteBase):
    @property
    def platform_cert_store_works(self) -> bool:
        return sys.platform != "win32"


class TestTunnelingHeadersMaxsize:
    """Tests for the DOWNLOAD_HEADERS_MAXSIZE limit that
    ``_TunnelingTCP4ClientEndpoint`` applies to the response head of the proxy,
    which no HTTP client parses for us."""

    def _get_endpoint(self, headers_maxsize: int) -> _TunnelingTCP4ClientEndpoint:
        from twisted.internet import reactor

        endpoint = _TunnelingTCP4ClientEndpoint(
            reactor=cast("Any", reactor),
            host="example.com",
            port=443,
            proxyConf=("proxy.example.com", 8080, None),
            contextFactory=cast("Any", None),
            headersMaxsize=headers_maxsize,
        )
        endpoint._protocol = cast("Any", Mock())
        endpoint._protocolDataReceived = Mock()
        return endpoint

    def test_over_maxsize(self) -> None:
        endpoint = self._get_endpoint(1024)
        failures: list[Failure] = []
        endpoint._tunnelReadyDeferred.addErrback(failures.append)

        # A proxy response head that never ends.
        for _ in range(3):
            endpoint.processProxyResponse(b"a" * 512)

        assert len(failures) == 1
        assert failures[0].check(ResponseHeadersTooLargeError)
        assert "1024" in str(failures[0].value)
        assert "CONNECT example.com:443" in str(failures[0].value)
        endpoint._protocol.transport.loseConnection.assert_called_once()  # type: ignore[union-attr]

    def test_under_maxsize(self) -> None:
        endpoint = self._get_endpoint(1024)
        failures: list[Failure] = []
        endpoint._tunnelReadyDeferred.addErrback(failures.append)

        endpoint.processProxyResponse(b"a" * 512)

        assert not failures

    def test_maxsize_disabled(self) -> None:
        endpoint = self._get_endpoint(0)
        failures: list[Failure] = []
        endpoint._tunnelReadyDeferred.addErrback(failures.append)

        for _ in range(3):
            endpoint.processProxyResponse(b"a" * 512)

        assert not failures


class TestScrapyHTTP11ClientProtocol:
    """Tests for the response header size limiting that
    ``_ScrapyHTTP11ClientProtocol`` installs on the response parser that
    Twisted builds for each request."""

    @staticmethod
    def _get_protocol() -> _ScrapyHTTP11ClientProtocol:
        protocol = _ScrapyHTTP11ClientProtocol(lambda _: None, 64 * 1024, 32 * 1024)
        protocol.makeConnection(StringTransport())  # type: ignore[no-untyped-call]
        return protocol

    @staticmethod
    def _get_request() -> TxClientRequest:
        return TxClientRequest(
            b"GET", b"/", TxHeaders({b"host": [b"example.com"]}), None
        )

    def test_parser_is_limited(self) -> None:
        protocol = self._get_protocol()
        protocol.request(self._get_request())
        assert protocol._parser is not None
        assert protocol._parser.MAX_LENGTH == 64 * 1024
        # _limit_response_headers() overrides these on the instance.
        assert "lineReceived" in vars(protocol._parser)
        assert "lineLengthExceeded" in vars(protocol._parser)

    def test_refused_request_keeps_previous_parser_limits(self) -> None:
        """A request that Twisted refuses leaves the parser of the previous
        request untouched, so that its size counter is not reset while its
        response is still being read."""
        protocol = self._get_protocol()
        protocol.request(self._get_request())
        parser = protocol._parser
        assert parser is not None
        line_received = vars(parser)["lineReceived"]

        # A second request over the same connection is refused, as the first one
        # is still in progress.
        deferred = protocol.request(self._get_request())
        failures: list[Failure] = []
        deferred.addErrback(failures.append)

        assert len(failures) == 1
        assert failures[0].check(RequestNotSent)
        assert protocol._parser is parser
        assert vars(parser)["lineReceived"] is line_received


class _CannedConnectProxy(Protocol):
    """Answers any request with a canned response."""

    factory: _CannedConnectProxyFactory

    def dataReceived(self, data: bytes) -> None:
        from twisted.internet import reactor

        assert self.transport
        response = self.factory.response
        if not self.factory.split_at:
            self.transport.write(response)
            return
        self.transport.write(response[: self.factory.split_at])
        reactor.callLater(0.1, self.transport.write, response[self.factory.split_at :])


class _CannedConnectProxyFactory(Factory):
    protocol = _CannedConnectProxy  # type: ignore[assignment]

    def __init__(self, response: bytes, split_at: int = 0):
        self.response = response
        self.split_at = split_at


@asynccontextmanager
async def _canned_proxy(response: bytes, split_at: int = 0) -> AsyncGenerator[str]:
    from twisted.internet import reactor

    port = reactor.listenTCP(
        0, _CannedConnectProxyFactory(response, split_at), interface="127.0.0.1"
    )
    try:
        yield f"http://127.0.0.1:{port.getHost().port}"
    finally:
        await maybe_deferred_to_future(port.stopListening())


@asynccontextmanager
async def _get_dh() -> AsyncGenerator[HTTP11DownloadHandler]:
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    dh = build_from_crawler(HTTP11DownloadHandler, crawler)
    try:
        yield dh
    finally:
        await dh.close()


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
    async def test_proxy_connection_refused(self) -> None:
        request = Request(
            "https://example.com", meta={"proxy": "http://127.0.0.1:65432"}
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
