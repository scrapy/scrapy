"""Tests for scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Request
from tests.test_downloader_handlers_http_base import (
    TestHttpBase,
    TestHttpProxyBase,
    TestHttpsBase,
    TestHttpsCustomCiphersBase,
    TestHttpsInvalidDNSIdBase,
    TestHttpsInvalidDNSPatternBase,
    TestHttpsWrongHostnameBase,
    TestHttpWithCrawlerBase,
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
        # the import will fail if httpx is not installed
        from scrapy.core.downloader.handlers._httpx import (  # noqa: PLC0415
            HttpxDownloadHandler,
        )

        return HttpxDownloadHandler


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

    @coroutine_test
    async def test_unsupported_proxy(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        meta = {"proxy": "127.0.0.2"}
        request = Request(mockserver.url("/text"), meta=meta)
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"Works"
        assert (
            "The 'proxy' request meta key is not supported by HttpxDownloadHandler"
            in caplog.text
        )


class TestHttps(HttpxDownloadHandlerMixin, TestHttpsBase):
    handler_supports_bindaddress_meta = False
    tls_log_message = "SSL connection to 127.0.0.1 using protocol TLSv1.3, cipher"

    @pytest.mark.skip(reason="The check is Twisted-specific")
    def test_verify_certs_deprecated(self):
        pass


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


class TestHttpWithCrawler(TestHttpWithCrawlerBase):
    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return {
            "DOWNLOAD_HANDLERS": {
                "http": "scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler",
                "https": "scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler",
            }
        }


class TestHttpsWithCrawler(TestHttpWithCrawler):
    is_secure = True

    @pytest.mark.skip(reason="response.certificate is not implemented")
    @coroutine_test
    async def test_response_ssl_certificate(self, mockserver: MockServer) -> None:
        pass


@pytest.mark.skip(reason="Proxy support is not implemented yet")
class TestHttpProxy(HttpxDownloadHandlerMixin, TestHttpProxyBase):
    pass


@pytest.mark.skip(reason="Proxy support is not implemented yet")
class TestHttpsProxy(HttpxDownloadHandlerMixin, TestHttpProxyBase):
    is_secure = True
