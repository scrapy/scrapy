"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pytest
from twisted.internet.error import ConnectionClosed
from twisted.internet.protocol import Factory, Protocol

from scrapy import Spider
from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler, TunnelError
from scrapy.crawler import Crawler
from scrapy.exceptions import (
    DownloadConnectionRefusedError,
    DownloadFailedError,
    NotConfigured,
)
from scrapy.http import Request
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.mockserver.utils import _free_port
from tests.test_downloader_handlers_http_base import (
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

    from twisted.internet.interfaces import IAddress

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


@pytest.mark.requires_mitmproxy
class TestMitmProxy(HTTP11DownloadHandlerMixin, TestMitmProxyBase):
    pass


@pytest.mark.requires_internet
class TestRealWebsite(HTTP11DownloadHandlerMixin, TestRealWebsiteBase):
    @property
    def platform_cert_store_works(self) -> bool:
        return sys.platform != "win32"


class _FaultyProxyProtocol(Protocol):
    """A CONNECT proxy that misbehaves once it receives the CONNECT request, to
    exercise the error paths of the tunneling code."""

    def __init__(self, behavior: str) -> None:
        self._behavior = behavior
        self._buffer = b""
        self._reacted = False

    def dataReceived(self, data: bytes) -> None:
        if self._reacted:
            return
        self._buffer += data
        if b"\r\n\r\n" not in self._buffer:
            return
        self._reacted = True
        assert self.transport is not None
        if self._behavior == "close":
            # Drop the connection instead of answering the CONNECT request.
            self.transport.loseConnection()
        elif self._behavior == "garbage":
            # Answer with something that is not a valid HTTP status line.
            self.transport.write(b"NOT-A-PROXY-RESPONSE\r\n\r\n")
        elif self._behavior == "trailing":
            # Answer success but append extra bytes right after the headers, so
            # that they are handed over to the tunneled protocol.
            self.transport.write(
                b"HTTP/1.1 200 Connection established\r\n\r\ntrailing-bytes"
            )


class _FaultyProxyFactory(Factory):
    def __init__(self, behavior: str) -> None:
        self._behavior = behavior

    def buildProtocol(self, addr: IAddress) -> _FaultyProxyProtocol:
        return _FaultyProxyProtocol(self._behavior)


class TestHttpsProxyTunnelErrors(HTTP11DownloadHandlerMixin):
    """Error paths of the HTTP CONNECT tunnel used for HTTPS-over-proxy."""

    @asynccontextmanager
    async def _download_handler(self) -> AsyncGenerator[DownloadHandlerProtocol]:
        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        dh = build_from_crawler(self.download_handler_cls, crawler)
        try:
            yield dh
        finally:
            await dh.close()

    @asynccontextmanager
    async def _faulty_proxy(self, behavior: str) -> AsyncGenerator[str]:
        from twisted.internet import reactor

        port = reactor.listenTCP(
            0, _FaultyProxyFactory(behavior), interface="127.0.0.1"
        )
        try:
            yield f"http://127.0.0.1:{port.getHost().port}"
        finally:
            await maybe_deferred_to_future(port.stopListening())

    @coroutine_test
    async def test_proxy_connection_refused(self) -> None:
        """Connecting to the proxy itself fails."""
        # Nothing is listening on this port.
        proxy = f"http://127.0.0.1:{_free_port()}"
        request = Request(
            "https://example.com/", meta={"proxy": proxy, "download_timeout": 20}
        )
        async with self._download_handler() as dh:
            with pytest.raises(DownloadConnectionRefusedError):
                await dh.download_request(request)

    @coroutine_test
    async def test_proxy_closes_connection(self) -> None:
        """The proxy drops the connection instead of answering CONNECT."""
        async with self._faulty_proxy("close") as proxy:
            request = Request(
                "https://example.com/", meta={"proxy": proxy, "download_timeout": 20}
            )
            async with self._download_handler() as dh:
                # The tunnel is never established, so the connection-lost reason
                # surfaces directly.
                with pytest.raises(ConnectionClosed):
                    await dh.download_request(request)

    @coroutine_test
    async def test_proxy_invalid_response(self) -> None:
        """The proxy answers CONNECT with something that is not a status line."""
        async with self._faulty_proxy("garbage") as proxy:
            request = Request(
                "https://example.com/", meta={"proxy": proxy, "download_timeout": 20}
            )
            async with self._download_handler() as dh:
                with pytest.raises(TunnelError):
                    await dh.download_request(request)

    @coroutine_test
    async def test_proxy_trailing_bytes(self) -> None:
        """The proxy appends bytes right after a successful CONNECT response, so
        they must be handed over to the tunneled protocol."""
        async with self._faulty_proxy("trailing") as proxy:
            request = Request(
                "https://example.com/", meta={"proxy": proxy, "download_timeout": 20}
            )
            async with self._download_handler() as dh:
                # The trailing bytes corrupt the destination TLS handshake, so
                # the download fails; what matters is that they were forwarded.
                with pytest.raises(DownloadFailedError):
                    await dh.download_request(request)
