"""Tests for scrapy.core.downloader.handlers.http10.HTTP10DownloadHandler."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scrapy.core.downloader.handlers.http10 import HTTP10DownloadHandler
from scrapy.http import Request
from scrapy.utils.defer import deferred_f_from_coro_f
from tests.test_downloader_handlers_http_base import TestHttpBase, TestHttpProxyBase

if TYPE_CHECKING:
    from scrapy.core.downloader.handlers import DownloadHandlerProtocol
    from tests.mockserver.http import MockServer


class HTTP10DownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return HTTP10DownloadHandler


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestHttp10(HTTP10DownloadHandlerMixin, TestHttpBase):
    """HTTP 1.0 test case"""

    @deferred_f_from_coro_f
    async def test_protocol(self, mockserver: MockServer) -> None:
        request = Request(
            mockserver.url("/host", is_secure=self.is_secure), method="GET"
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.protocol == "HTTP/1.0"


class TestHttps10(TestHttp10):
    is_secure = True


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestHttp10Proxy(HTTP10DownloadHandlerMixin, TestHttpProxyBase):
    @deferred_f_from_coro_f
    async def test_download_with_proxy_https_timeout(self):
        pytest.skip("Not implemented")

    @deferred_f_from_coro_f
    async def test_download_with_proxy_without_http_scheme(self):
        pytest.skip("Not implemented")
