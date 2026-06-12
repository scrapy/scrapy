"""Tests for scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from scrapy import Request
from scrapy.core.downloader.handlers._httpx import (
    HAS_HTTP2,
    HAS_SOCKS,
    HttpxDownloadHandler,
)
from scrapy.exceptions import DownloadFailedError
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
    from scrapy.core.downloader.handlers import DownloadHandlerProtocol
    from tests.mockserver.http import MockServer


pytestmark = pytest.mark.only_asyncio

pytest.importorskip("httpx")


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

    @coroutine_test
    async def test_proxy_auth_header_preserved_for_retries(self) -> None:
        class Stream:
            async def __aenter__(self) -> None:
                return None

            async def __aexit__(self, *args: object) -> None:
                return None

        class Client:
            def __init__(self) -> None:
                self.headers: list[tuple[str, str]] | None = None
                self.proxy: str | None = None

            def stream(self, *args: Any, **kwargs: Any) -> Stream:
                self.headers = kwargs["headers"]
                return Stream()

        request = Request(
            "http://example.com/",
            headers={
                "Proxy-Authorization": "Basic dXNlcjpwYXNz",
                "X-Test": "test",
            },
            meta={"proxy": "http://proxy.example:3128"},
        )
        client = Client()
        handler: Any = HttpxDownloadHandler.__new__(HttpxDownloadHandler)
        handler._proxy_auth_encoding = "latin-1"

        def get_client(proxy: str | None) -> Client:
            client.proxy = proxy
            return client

        handler._get_client = get_client

        async with handler._make_request(request, timeout=1.0):
            pass

        assert client.proxy == "http://user:pass@proxy.example:3128"
        assert client.headers == [("X-Test", "test")]
        assert request.headers[b"Proxy-Authorization"] == b"Basic dXNlcjpwYXNz"
        assert (
            handler._extract_proxy_url_with_creds(request)
            == "http://user:pass@proxy.example:3128"
        )


class TestHttpsProxy(TestHttpProxy):
    is_secure = True


@pytest.mark.requires_mitmproxy
class TestMitmProxy(HttpxDownloadHandlerMixin, TestMitmProxyBase):
    handler_supports_socks = HAS_SOCKS


@pytest.mark.requires_internet
class TestRealWebsite(HttpxDownloadHandlerMixin, TestRealWebsiteBase):
    pass
