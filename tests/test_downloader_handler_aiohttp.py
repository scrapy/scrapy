"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from scrapy.core.downloader.handlers.aiohttp import AiohttpDownloadHandler
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


class AiohttpDownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return AiohttpDownloadHandler


DATALOSS_SKIP_REASON = "TODO support for dataloss handling"
MAXSIZE_SKIP_REASON = "TODO support for maxsize handling"


class TestHttp11(AiohttpDownloadHandlerMixin, TestHttp11Base):
    def test_download_broken_content_cause_data_loss(self, url="broken"):
        pytest.skip(DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_cause_data_loss(self):
        pytest.skip(DATALOSS_SKIP_REASON)

    def test_download_broken_content_allow_data_loss(self, url="broken"):
        pytest.skip(DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_allow_data_loss(self):
        pytest.skip(DATALOSS_SKIP_REASON)

    def test_download_broken_content_allow_data_loss_via_setting(self, url="broken"):
        pytest.skip(DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_allow_data_loss_via_setting(self):
        pytest.skip(DATALOSS_SKIP_REASON)

    def test_download_with_maxsize(self):
        pytest.skip(MAXSIZE_SKIP_REASON)

    def test_download_with_maxsize_very_large_file(self):
        pytest.skip(MAXSIZE_SKIP_REASON)

    def test_download_with_maxsize_per_req(self):
        pytest.skip(MAXSIZE_SKIP_REASON)

    def test_download_with_small_maxsize_per_spider(self):
        pytest.skip(MAXSIZE_SKIP_REASON)


class TestHttps11(AiohttpDownloadHandlerMixin, TestHttps11Base):
    def test_download_broken_content_cause_data_loss(self, url="broken"):
        pytest.skip(DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_cause_data_loss(self):
        pytest.skip(DATALOSS_SKIP_REASON)

    def test_download_broken_content_allow_data_loss(self, url="broken"):
        pytest.skip(DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_allow_data_loss(self):
        pytest.skip(DATALOSS_SKIP_REASON)

    def test_download_broken_content_allow_data_loss_via_setting(self, url="broken"):
        pytest.skip(DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_allow_data_loss_via_setting(self):
        pytest.skip(DATALOSS_SKIP_REASON)

    def test_download_with_maxsize(self):
        pytest.skip(MAXSIZE_SKIP_REASON)

    def test_download_with_maxsize_very_large_file(self):
        pytest.skip(MAXSIZE_SKIP_REASON)

    def test_download_with_maxsize_per_req(self):
        pytest.skip(MAXSIZE_SKIP_REASON)

    def test_download_with_small_maxsize_per_spider(self):
        pytest.skip(MAXSIZE_SKIP_REASON)

    def test_tls_logging(self):
        pytest.skip("TODO: support for TLS logging")


class TestSimpleHttps(AiohttpDownloadHandlerMixin, TestSimpleHttpsBase):
    pass


class Https11WrongHostnameTestCase(
    AiohttpDownloadHandlerMixin, TestHttpsWrongHostnameBase
):
    pass


class Https11InvalidDNSId(AiohttpDownloadHandlerMixin, TestHttpsInvalidDNSIdBase):
    pass


class Https11InvalidDNSPattern(
    AiohttpDownloadHandlerMixin, TestHttpsInvalidDNSPatternBase
):
    pass


@pytest.mark.skip("TODO: support for custom ciphers")
class Https11CustomCiphers(AiohttpDownloadHandlerMixin, TestHttpsCustomCiphersBase):
    pass


class TestHttp11MockServer(TestHttpMockServerBase):
    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return {
            "DOWNLOAD_HANDLERS": {
                "https": "scrapy.core.downloader.handlers.aiohttp.AiohttpDownloadHandler"
            }
        }


class TestHttp11Proxy(AiohttpDownloadHandlerMixin, TestHttpProxyBase):
    def test_download_with_proxy_https_timeout(self):
        pytest.skip("TODO")

    def test_download_with_proxy_without_http_scheme(self):
        pytest.skip("TODO")
