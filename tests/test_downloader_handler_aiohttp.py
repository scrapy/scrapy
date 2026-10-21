from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import aiodns
import pytest

from scrapy import Request
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
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy.core.downloader.handlers import DownloadHandlerProtocol
    from tests.mockserver.http import MockServer

pytestmark = pytest.mark.only_asyncio


class AiohttpDownloadHandlerMixin:
    handler_supports_partial_response_on_timeout = True

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
    handler_non_utf8_request_header_handling = "replace"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only workaround")
    @coroutine_test
    async def test_port_not_resolved(
        self, mockserver: MockServer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The URL port is used even if resolving it as a service gives a
        different one, as it can on Windows."""
        real_getaddrinfo = aiodns.DNSResolver.getaddrinfo

        def getaddrinfo(self, host, port=None, **kwargs):
            # a services database match on Windows returns the port with its
            # bytes swapped
            if port:
                port = ((port & 0xFF) << 8) | (port >> 8)
            return real_getaddrinfo(self, host, port=port, **kwargs)

        monkeypatch.setattr(aiodns.DNSResolver, "getaddrinfo", getaddrinfo)
        request = Request(mockserver.url("/text").replace("127.0.0.1", "localhost"))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"Works"


class TestHttps(AiohttpDownloadHandlerMixin, TestHttpsBase):
    handler_supports_bindaddress_meta = False
    handler_bad_header_handling = "fail"
    handler_non_utf8_request_header_handling = "replace"
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


@pytest.mark.requires_mitmproxy
class TestMitmProxy(AiohttpDownloadHandlerMixin, TestMitmProxyBase):
    handler_supports_socks: bool = False


@pytest.mark.requires_internet
class TestRealWebsite(AiohttpDownloadHandlerMixin, TestRealWebsiteBase):
    pass
