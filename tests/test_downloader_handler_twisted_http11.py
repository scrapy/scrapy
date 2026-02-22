"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from twisted.internet.defer import succeed

from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.http import Request, Response
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


pytestmark = pytest.mark.requires_reactor


class HTTP11DownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return HTTP11DownloadHandler


class TestHttp11(HTTP11DownloadHandlerMixin, TestHttp11Base):
    @coroutine_test
    async def test_download_bind_address_setting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_kwargs = {}

        class DummyAgent:
            def __init__(self, **kwargs) -> None:
                captured_kwargs.update(kwargs)

            def download_request(self, request: Request):
                return succeed(Response(request.url))

        monkeypatch.setattr(
            "scrapy.core.downloader.handlers.http11.ScrapyAgent", DummyAgent
        )
        crawler = get_crawler(
            DefaultSpider, {"DOWNLOAD_BIND_ADDRESS": ("127.0.0.2", 0)}
        )
        crawler.spider = crawler._create_spider()
        download_handler = build_from_crawler(HTTP11DownloadHandler, crawler)
        try:
            await download_handler.download_request(Request("http://example.com"))
        finally:
            await download_handler.close()

        assert captured_kwargs["bindAddress"] == ("127.0.0.2", 0)


class TestHttps11(HTTP11DownloadHandlerMixin, TestHttps11Base):
    pass


class TestSimpleHttps(HTTP11DownloadHandlerMixin, TestSimpleHttpsBase):
    pass


class TestHttps11WrongHostname(HTTP11DownloadHandlerMixin, TestHttpsWrongHostnameBase):
    pass


class TestHttps11InvalidDNSId(HTTP11DownloadHandlerMixin, TestHttpsInvalidDNSIdBase):
    pass


class TestHttps11InvalidDNSPattern(
    HTTP11DownloadHandlerMixin, TestHttpsInvalidDNSPatternBase
):
    pass


class TestHttps11CustomCiphers(HTTP11DownloadHandlerMixin, TestHttpsCustomCiphersBase):
    pass


class TestHttp11WithCrawler(TestHttpWithCrawlerBase):
    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return {
            "DOWNLOAD_HANDLERS": {
                "http": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
                "https": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
            }
        }


class TestHttps11WithCrawler(TestHttp11WithCrawler):
    is_secure = True


class TestHttp11Proxy(HTTP11DownloadHandlerMixin, TestHttpProxyBase):
    pass
