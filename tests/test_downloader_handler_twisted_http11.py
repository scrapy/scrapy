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


DH = HTTP11DownloadHandler


class TestHttp11(TestHttp11Base):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return DH


class TestHttps11(TestHttps11Base):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return DH


class TestSimpleHttps(TestSimpleHttpsBase):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return DH


class Https11WrongHostnameTestCase(TestHttpsWrongHostnameBase):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return DH


class Https11InvalidDNSId(TestHttpsInvalidDNSIdBase):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return DH


class Https11InvalidDNSPattern(TestHttpsInvalidDNSPatternBase):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return DH


class Https11CustomCiphers(TestHttpsCustomCiphersBase):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return DH


class TestHttp11MockServer(TestHttpMockServerBase):
    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return None  # default handler settings


class TestHttp11Proxy(TestHttpProxyBase):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return DH
