"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pytest
from twisted.internet.protocol import Factory, Protocol
from twisted.web._newclient import BadHeaders

from scrapy import Request, Spider
from scrapy.core.downloader.handlers.http11 import (
    HTTP11DownloadHandler,
    TunnelError,
    _ScrapyTxHeaders,
    _ScrapyTxRequest,
)
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
from tests.utils.raw_http import capturing_server

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from scrapy.core.downloader.handlers import DownloadHandlerProtocol
    from tests.utils.raw_http import _CapturingServer


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


async def _capture(
    request_kwargs: dict[str, Any], *, via_proxy: bool = False
) -> _CapturingServer:
    with capturing_server() as server:
        if via_proxy:
            request_kwargs.setdefault("meta", {})["proxy"] = server.url
        else:
            request_kwargs.setdefault("url", server.url + "/path")
        async with _get_dh() as dh:
            await dh.download_request(Request(**request_kwargs))
    return server


class TestWireHeaders:
    @coroutine_test
    async def test_default_order_get(self) -> None:
        server = await _capture({"headers": {"X-A": "1"}})
        assert server.header_names() == [b"X-A", b"Host"]

    @coroutine_test
    async def test_default_order_post(self) -> None:
        server = await _capture(
            {"method": "POST", "body": b"abc", "headers": {"X-A": "1"}}
        )
        assert server.header_lines() == [
            (b"Content-Length", b"3"),
            (b"X-A", b"1"),
            (b"Host", server.url.removeprefix("http://").encode()),
        ]

    @coroutine_test
    async def test_explicit_host_keeps_position_and_case(self) -> None:
        with capturing_server() as server:
            host = server.url.removeprefix("http://")
            request = Request(
                server.url, headers=[("X-A", "1"), ("host", host), ("X-B", "2")]
            )
            async with _get_dh() as dh:
                await dh.download_request(request)
        assert server.header_names() == [b"X-A", b"host", b"X-B"]

    @coroutine_test
    async def test_post_user_content_length_not_duplicated(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        server = await _capture(
            {"method": "POST", "body": b"abc", "headers": {"content-length": "3"}}
        )
        assert server.header_lines()[0] == (b"content-length", b"3")
        assert server.header_names().count(b"content-length") == 1
        assert "Ignoring" not in caplog.text

    @coroutine_test
    async def test_post_bad_user_content_length_replaced(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        server = await _capture(
            {"method": "POST", "body": b"abc", "headers": {"Content-Length": "10"}}
        )
        assert server.header_lines()[0] == (b"Content-Length", b"3")
        assert server.header_names().count(b"Content-Length") == 1
        assert "Ignoring the b'Content-Length' request header" in caplog.text

    @coroutine_test
    async def test_get_user_content_length_kept(self) -> None:
        server = await _capture({"headers": {"Content-Length": "0"}})
        assert server.header_lines()[0] == (b"Content-Length", b"0")
        assert server.header_names().count(b"Content-Length") == 1

    @coroutine_test
    async def test_proxy(self) -> None:
        server = await _capture(
            {
                "url": "http://example.com/path",
                "headers": [("x-b", "2"), ("X-A", "1")],
            },
            via_proxy=True,
        )
        assert server.request_line() == b"GET http://example.com/path HTTP/1.1"
        assert server.header_lines() == [
            (b"x-b", b"2"),
            (b"X-A", b"1"),
            (b"Host", b"example.com"),
        ]


class _FakeTransport:
    def __init__(self) -> None:
        self.data = b""

    def writeSequence(self, data: list[bytes]) -> None:
        self.data += b"".join(data)


class TestScrapyTxRequest:
    def test_headers_copy(self) -> None:
        headers = _ScrapyTxHeaders({b"x-a": [b"1"]}, names={b"x-a": b"x-a"})
        copy = headers.copy()
        assert isinstance(copy, _ScrapyTxHeaders)
        assert copy._names == headers._names
        assert list(copy.getAllRawHeaders()) == list(headers.getAllRawHeaders())

    def test_not_persistent(self, caplog: pytest.LogCaptureFixture) -> None:
        headers = _ScrapyTxHeaders(
            {b"Host": [b"example.com"], b"connection": [b"keep-alive"]},
            names={b"host": b"Host", b"connection": b"connection"},
        )
        request = _ScrapyTxRequest(b"GET", b"/", headers, None, persistent=False)  # type: ignore[no-untyped-call]
        transport = _FakeTransport()
        request._writeHeaders(transport, None)
        assert transport.data == (
            b"GET / HTTP/1.1\r\nconnection: close\r\nHost: example.com\r\n\r\n"
        )
        assert "Ignoring the b'connection' request header" in caplog.text

    def test_chunked_replaces_user_content_length(self) -> None:
        headers = _ScrapyTxHeaders(
            {b"Host": [b"example.com"], b"Content-Length": [b"3"]},
            names={b"host": b"Host", b"content-length": b"Content-Length"},
        )
        request = _ScrapyTxRequest(b"POST", b"/", headers, None, persistent=True)  # type: ignore[no-untyped-call]
        transport = _FakeTransport()
        request._writeHeaders(transport, b"Transfer-Encoding: chunked\r\n")
        assert transport.data == (
            b"POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n"
            b"Host: example.com\r\n\r\n"
        )

    def test_host_required(self) -> None:
        request = _ScrapyTxRequest(  # type: ignore[no-untyped-call]
            b"GET", b"/", _ScrapyTxHeaders(), None, persistent=True
        )
        with pytest.raises(BadHeaders):
            request._writeHeaders(_FakeTransport(), None)
