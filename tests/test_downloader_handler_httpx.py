"""Tests for scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Request
from tests.test_downloader_handlers_http_base import (
    TestHttp11Base,
    TestHttpProxyBase,
    TestHttps11Base,
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


pytest.importorskip("httpx")


class HttpxDownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        # the import will fail if httpx is not installed
        from scrapy.core.downloader.handlers._httpx import (  # noqa: PLC0415
            HttpxDownloadHandler,
        )

        return HttpxDownloadHandler


class TestHttp11(HttpxDownloadHandlerMixin, TestHttp11Base):
    @coroutine_test
    async def test_unsupported_bindaddress(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        meta = {"bindaddress": "127.0.0.2"}
        request = Request(mockserver.url("/text"), meta=meta)
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"Works"
        assert (
            "The 'bindaddress' request meta key is not supported by HttpxDownloadHandler"
            in caplog.text
        )

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


class TestHttps11(HttpxDownloadHandlerMixin, TestHttps11Base):
    tls_log_message = "SSL connection to 127.0.0.1 using protocol TLSv1.3, cipher"


class TestSimpleHttps(HttpxDownloadHandlerMixin, TestSimpleHttpsBase):
    pass


class Https11WrongHostnameTestCase(
    HttpxDownloadHandlerMixin, TestHttpsWrongHostnameBase
):
    pass


class Https11InvalidDNSId(HttpxDownloadHandlerMixin, TestHttpsInvalidDNSIdBase):
    pass


class Https11InvalidDNSPattern(
    HttpxDownloadHandlerMixin, TestHttpsInvalidDNSPatternBase
):
    pass


class Https11CustomCiphers(HttpxDownloadHandlerMixin, TestHttpsCustomCiphersBase):
    pass


class TestHttp11WithCrawler(TestHttpWithCrawlerBase):
    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return {
            "DOWNLOAD_HANDLERS": {
                "http": "scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler",
                "https": "scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler",
            }
        }


class TestHttps11WithCrawler(TestHttp11WithCrawler):
    is_secure = True

    @pytest.mark.skip(reason="response.certificate is not implemented")
    @coroutine_test
    async def test_response_ssl_certificate(self, mockserver: MockServer) -> None:
        pass


@pytest.mark.skip(reason="Proxy support is not implemented yet")
class TestHttp11Proxy(HttpxDownloadHandlerMixin, TestHttpProxyBase):
    pass


@pytest.mark.skip(reason="Proxy support is not implemented yet")
class TestHttps11Proxy(HttpxDownloadHandlerMixin, TestHttpProxyBase):
    is_secure = True
