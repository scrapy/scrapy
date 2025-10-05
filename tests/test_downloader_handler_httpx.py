"""Tests for scrapy.core.downloader.handlers.httpx.HTTPXDownloadHandler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Running all pre-existing twisted HTTP download handler tests under HTTPX to avoid writing duplicate tests
from tests.test_downloader_handler_twisted_http2 import TestHttps2, TestHttp2MockServer
from tests.test_downloader_handler_twisted_http10 import TestHttp10, TestHttps10
from tests.test_downloader_handler_twisted_http11 import TestHttp11, TestHttps11
from tests.test_downloader_handlers_http_base import TestHttpMockServerBase

if TYPE_CHECKING:
    from scrapy.core.downloader.handlers import DownloadHandlerProtocol

class TestHttps2x(TestHttps2):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        from scrapy.core.downloader.handlers.httpx import HTTPXDownloadHandler

        return HTTPXDownloadHandler
    



class TestHttp11x(TestHttp11):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        from scrapy.core.downloader.handlers.httpx import HTTPXDownloadHandler

        return HTTPXDownloadHandler


class TestHttps11x(TestHttps11):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        from scrapy.core.downloader.handlers.httpx import HTTPXDownloadHandler

        return HTTPXDownloadHandler


class TestHttp10x(TestHttp10):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        from scrapy.core.downloader.handlers.httpx import HTTPXDownloadHandler

        return HTTPXDownloadHandler


class TestHttps10x(TestHttps10):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        from scrapy.core.downloader.handlers.httpx import HTTPXDownloadHandler

        return HTTPXDownloadHandler
