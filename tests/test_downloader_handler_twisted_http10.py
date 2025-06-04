"""Tests for scrapy.core.downloader.handlers.http10.HTTP10DownloadHandler."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scrapy.core.downloader.handlers.http10 import HTTP10DownloadHandler
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.defer import deferred_f_from_coro_f
from tests.test_downloader_handlers_http_base import TestHttpBase, TestHttpProxyBase

if TYPE_CHECKING:
    from scrapy.core.downloader.handlers import DownloadHandlerProtocol


class HTTP10DownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return HTTP10DownloadHandler


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestHttp10(HTTP10DownloadHandlerMixin, TestHttpBase):
    """HTTP 1.0 test case"""

    @deferred_f_from_coro_f
    async def test_protocol(self):
        request = Request(self.getURL("host"), method="GET")
        response = await self.download_request(request, Spider("foo"))
        assert response.protocol == "HTTP/1.0"


class TestHttps10(TestHttp10):
    scheme = "https"


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestHttp10Proxy(HTTP10DownloadHandlerMixin, TestHttpProxyBase):
    def test_download_with_proxy_https_timeout(self):
        pytest.skip("Not implemented")

    def test_download_with_proxy_without_http_scheme(self):
        pytest.skip("Not implemented")
