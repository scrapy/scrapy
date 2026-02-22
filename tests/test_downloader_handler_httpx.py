"""Tests for scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Request
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
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
    async def test_download_bind_address_setting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from scrapy.core.downloader.handlers import _httpx  # noqa: PLC0415

        transport_kwargs = {}

        class DummyTransport:
            def __init__(self, **kwargs) -> None:
                transport_kwargs.update(kwargs)

        class DummyClient:
            def __init__(self, **kwargs) -> None:
                self.transport = kwargs.get("transport")

            async def aclose(self) -> None:
                return None

        monkeypatch.setattr(_httpx.httpx, "AsyncHTTPTransport", DummyTransport)
        monkeypatch.setattr(_httpx.httpx, "AsyncClient", DummyClient)
        crawler = get_crawler(
            DefaultSpider, {"DOWNLOAD_BIND_ADDRESS": ("127.0.0.2", 0)}
        )
        crawler.spider = crawler._create_spider()
        download_handler = build_from_crawler(self.download_handler_cls, crawler)
        await download_handler.close()

        assert transport_kwargs["local_address"] == "127.0.0.2"

    @coroutine_test
    async def test_unsupported_bindaddress(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        meta = {"bindaddress": ("127.0.0.2", 0)}
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
