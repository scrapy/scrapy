from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import pytest

from scrapy.core.downloader.handlers._aiohttp import AiohttpDownloadHandler
from tests.utils.bases.download_handlers_http import (
    TestHttpBase,
    TestHttpProxyBase,
    TestHttpsBase,
    TestHttpsCustomCiphersBase,
    TestHttpsDefaultCiphersBase,
    TestHttpsInvalidDNSIdBase,
    TestHttpsInvalidDNSPatternBase,
    TestHttpsTLSVersionBase,
    TestHttpsWrongHostnameBase,
    TestHttpWithCrawlerBase,
    TestMitmProxyBase,
    TestRealWebsiteBase,
    TestSimpleHttpsBase,
)

if TYPE_CHECKING:
    from scrapy.core.downloader.handlers import DownloadHandlerProtocol

pytestmark = pytest.mark.only_asyncio


class AiohttpDownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return AiohttpDownloadHandler

    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return {
            "DOWNLOAD_HANDLERS": {
                "http": "scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler",
                "https": "scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler",
            }
        }


class TestHttp(AiohttpDownloadHandlerMixin, TestHttpBase):
    handler_supports_bindaddress_meta = False
    handler_bad_header_handling = "fail"


class TestHttps(AiohttpDownloadHandlerMixin, TestHttpsBase):
    handler_supports_bindaddress_meta = False
    handler_bad_header_handling = "fail"
    tls_log_message = "SSL connection to 127.0.0.1 using protocol TLSv1.3, cipher"

    @pytest.mark.skip(reason="The check is Twisted-specific")
    def test_verify_certs_deprecated(self) -> None:  # type: ignore[override]
        pass


class TestSimpleHttps(AiohttpDownloadHandlerMixin, TestSimpleHttpsBase):
    pass


class TestHttpsWrongHostname(AiohttpDownloadHandlerMixin, TestHttpsWrongHostnameBase):
    pass


class TestHttpsInvalidDNSId(AiohttpDownloadHandlerMixin, TestHttpsInvalidDNSIdBase):
    pass


class TestHttpsInvalidDNSPattern(
    AiohttpDownloadHandlerMixin, TestHttpsInvalidDNSPatternBase
):
    pass


class TestHttpsCustomCiphers(AiohttpDownloadHandlerMixin, TestHttpsCustomCiphersBase):
    pass


class TestHttpsDefaultCiphers(AiohttpDownloadHandlerMixin, TestHttpsDefaultCiphersBase):
    pass


class TestHttpsTLSVersion(AiohttpDownloadHandlerMixin, TestHttpsTLSVersionBase):
    pass


class TestHttpWithCrawler(AiohttpDownloadHandlerMixin, TestHttpWithCrawlerBase):
    pass


class TestHttpsWithCrawler(TestHttpWithCrawler):
    is_secure = True


class TestHttpProxy(AiohttpDownloadHandlerMixin, TestHttpProxyBase):
    pass


class TestHttpsProxy(AiohttpDownloadHandlerMixin, TestHttpProxyBase):
    is_secure = True

    @property
    def handler_supports_tls_in_tls(self) -> bool:
        return sys.version_info >= (3, 11)


@pytest.mark.requires_mitmproxy
class TestMitmProxy(AiohttpDownloadHandlerMixin, TestMitmProxyBase):
    handler_supports_socks: bool = False

    @property
    def handler_supports_tls_in_tls(self) -> bool:
        return sys.version_info >= (3, 11)


@pytest.mark.requires_internet
class TestRealWebsite(AiohttpDownloadHandlerMixin, TestRealWebsiteBase):
    pass
