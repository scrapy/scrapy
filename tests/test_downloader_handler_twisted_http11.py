"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from tests.test_downloader_handlers_http_base import (
    TestHttp11Base,
    TestHttpMockServerBase,
    TestHttpProxyBase,
    TestHttps11Base,
    TestHttpsCustomCiphersBase,
    TestHttpsInvalidDNSIdBase,
    TestHttpsInvalidDNSPatternBase,
    TestHttpsWrongHostnameBase,
    TestSimpleHttpsBase,
)

if TYPE_CHECKING:
    from scrapy.core.downloader.handlers import DownloadHandlerProtocol


class HTTP11DownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return HTTP11DownloadHandler


class TestHttp11(HTTP11DownloadHandlerMixin, TestHttp11Base):
    pass


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


class TestHttp11MockServer(TestHttpMockServerBase):
    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return None  # default handler settings


class TestHttp11Proxy(HTTP11DownloadHandlerMixin, TestHttpProxyBase):
    pass
