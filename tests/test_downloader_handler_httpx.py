"""Tests for scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler."""

from __future__ import annotations

import sys
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from scrapy import Request
from scrapy.core.downloader.handlers._httpx import (
    HAS_HTTP2,
    HAS_SOCKS,
    HttpxDownloadHandler,
)
from scrapy.exceptions import DownloadFailedError
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
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
    from scrapy.core.downloader.handlers import DownloadHandlerProtocol
    from tests.mockserver.http import MockServer


pytestmark = pytest.mark.only_asyncio

if find_spec("httpx2") is None and find_spec("httpx") is None:
    pytest.skip("Neither httpx2 nor httpx are installed", allow_module_level=True)


class HttpxDownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return HttpxDownloadHandler

    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return {
            "DOWNLOAD_HANDLERS": {
                "http": "scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler",
                "https": "scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler",
            }
        }


class TestHttp(HttpxDownloadHandlerMixin, TestHttpBase):
    handler_supports_bindaddress_meta = False
    handler_bad_header_handling = "fail"

    @pytest.mark.skipif(
        sys.platform == "darwin",
        reason="127.0.0.2 is not available on macOS by default",
    )
    @coroutine_test
    async def test_bind_address_port_warning(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        request = Request(mockserver.url("/client-ip"))
        async with self.get_dh(
            {"DOWNLOAD_BIND_ADDRESS": ("127.0.0.2", 12345)}
        ) as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"127.0.0.2"
        assert "DOWNLOAD_BIND_ADDRESS specifies a port (12345)" in caplog.text
        assert "Ignoring the port" in caplog.text


class TestHttps(HttpxDownloadHandlerMixin, TestHttpsBase):
    handler_supports_bindaddress_meta = False
    handler_bad_header_handling = "fail"
    tls_log_message = "SSL connection to 127.0.0.1 using protocol TLSv1.3, cipher"

    @pytest.mark.skip(reason="The check is Twisted-specific")
    def test_verify_certs_deprecated(self) -> None:  # type: ignore[override]
        pass


@pytest.mark.skipif(not HAS_HTTP2, reason="No HTTP/2 support in HttpxDownloadHandler")
class TestHttp2(TestHttps):
    http2 = True
    handler_supports_http2_dataloss = False

    default_handler_settings: ClassVar[dict[str, Any]] = {
        "HTTPX_HTTP2_ENABLED": True,
    }

    @coroutine_test
    async def test_protocol(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/host", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.protocol == "HTTP/2"

    @coroutine_test
    async def test_data_loss_handling(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/broken", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            with pytest.raises(DownloadFailedError):
                await download_handler.download_request(request)


class TestSimpleHttps(HttpxDownloadHandlerMixin, TestSimpleHttpsBase):
    pass


class TestHttpsWrongHostname(HttpxDownloadHandlerMixin, TestHttpsWrongHostnameBase):
    pass


class TestHttpsInvalidDNSId(HttpxDownloadHandlerMixin, TestHttpsInvalidDNSIdBase):
    pass


class TestHttpsInvalidDNSPattern(
    HttpxDownloadHandlerMixin, TestHttpsInvalidDNSPatternBase
):
    pass


class TestHttpsCustomCiphers(HttpxDownloadHandlerMixin, TestHttpsCustomCiphersBase):
    pass


class TestHttpsTLSVersion(HttpxDownloadHandlerMixin, TestHttpsTLSVersionBase):
    pass


class TestHttpWithCrawler(HttpxDownloadHandlerMixin, TestHttpWithCrawlerBase):
    pass


class TestHttpsWithCrawler(TestHttpWithCrawler):
    is_secure = True


class TestHttpProxy(HttpxDownloadHandlerMixin, TestHttpProxyBase):
    expected_http_proxy_request_body = b"http://example.com/"


class TestHttpsProxy(TestHttpProxy):
    is_secure = True


@pytest.mark.requires_mitmproxy
class TestMitmProxy(HttpxDownloadHandlerMixin, TestMitmProxyBase):
    handler_supports_socks = HAS_SOCKS


@pytest.mark.requires_internet
class TestRealWebsite(HttpxDownloadHandlerMixin, TestRealWebsiteBase):
    pass


@coroutine_test
async def test_proxy_clients() -> None:
    proxy = "http://proxy.example:8080"
    handler = build_from_crawler(HttpxDownloadHandler, get_crawler())
    try:
        client = handler._get_client(proxy, (("X-A", "1"),))
        assert handler._get_client(proxy, (("X-A", "1"),)) is client
        assert handler._get_client(proxy, (("X-A", "2"),)) is not client
        assert handler._get_client(proxy) is not client
        assert len(handler._proxy_clients) == 3
    finally:
        await handler.close()


@coroutine_test
async def test_proxy_headers_ignored_for_socks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    if not HAS_SOCKS:  # pragma: no cover
        pytest.skip("SOCKS support is not installed")
    handler = build_from_crawler(HttpxDownloadHandler, get_crawler())
    try:
        with caplog.at_level("WARNING"):
            handler._get_client("socks5://proxy.example:1080", (("X-A", "1"),))
    finally:
        await handler.close()
    assert "the SOCKS protocol has no headers" in caplog.text


@pytest.mark.parametrize(("concurrency", "expected"), [(16, 16), (0, None)])
@coroutine_test
async def test_pool_limits(concurrency: int, expected: int | None) -> None:
    crawler = get_crawler(settings_dict={"CONCURRENT_REQUESTS": concurrency})
    handler = build_from_crawler(HttpxDownloadHandler, crawler)
    try:
        assert handler._limits.max_connections == expected
        assert handler._limits.max_keepalive_connections == expected
    finally:
        await handler.close()
