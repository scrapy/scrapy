"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pytest
from twisted.internet.protocol import Factory, Protocol

from scrapy import Request, Spider
from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler, TunnelError
from scrapy.crawler import Crawler
from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadConnectionRefusedError,
    NotConfigured,
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

    handler_supports_custom_content_length = False


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
