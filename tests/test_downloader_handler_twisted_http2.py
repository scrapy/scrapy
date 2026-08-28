"""Tests for scrapy.core.downloader.handlers.http2.H2DownloadHandler."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import pytest
from twisted.internet.defer import DeferredList
from twisted.web.http import H2_ENABLED

from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import (
    DownloadFailedError,
    NotConfigured,
    UnsupportedURLSchemeError,
)
from scrapy.http import Request
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from tests.utils.bases.download_handlers_http import (
    TestHttpProxyBase,
    TestHttpsBase,
    TestHttpsCustomCiphersBase,
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


pytestmark = [
    pytest.mark.requires_reactor,  # H2DownloadHandler requires a reactor
    pytest.mark.skipif(
        not H2_ENABLED, reason="HTTP/2 support in Twisted is not enabled"
    ),
]


class H2DownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        # the import can fail when H2_ENABLED is False
        from scrapy.core.downloader.handlers.http2 import (  # noqa: PLC0415
            H2DownloadHandler,
        )

        return H2DownloadHandler

    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return {
            "DOWNLOAD_HANDLERS": {
                "http": None,
                "https": "scrapy.core.downloader.handlers.http2.H2DownloadHandler",
            }
        }


def test_not_configured_without_reactor() -> None:
    from scrapy.core.downloader.handlers.http2 import H2DownloadHandler  # noqa: PLC0415

    crawler = Crawler(Spider, {"TWISTED_REACTOR_ENABLED": False})
    with pytest.raises(NotConfigured):
        build_from_crawler(H2DownloadHandler, crawler)


class TestHttp2(H2DownloadHandlerMixin, TestHttpsBase):
    http2 = True
    handler_supports_http2_dataloss = False

    @coroutine_test
    async def test_protocol(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/host", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.protocol == "h2"

    @coroutine_test
    async def test_concurrent_requests_same_domain(
        self, mockserver: MockServer
    ) -> None:
        request1 = Request(mockserver.url("/text", is_secure=self.is_secure))
        request2 = Request(
            mockserver.url("/echo", is_secure=self.is_secure), method="POST"
        )
        async with self.get_dh() as download_handler:
            response1 = await download_handler.download_request(request1)
            assert response1.body == b"Works"
            response2 = await download_handler.download_request(request2)
            assert response2.headers["Content-Length"] == b"79"

    @coroutine_test
    async def test_parallel_requests_same_domain(self, mockserver: MockServer) -> None:
        url = mockserver.url("/connection-id", is_secure=self.is_secure)
        async with self.get_dh() as download_handler:
            results = await maybe_deferred_to_future(
                DeferredList(
                    [
                        deferred_from_coro(download_handler.download_request(request))
                        for request in (Request(url), Request(url))
                    ],
                    fireOnOneErrback=True,
                )
            )
        # the second request waited for the connection that the first one was
        # opening instead of opening a second one
        assert len({response.text for _, response in results}) == 1

    @pytest.mark.xfail(reason="https://github.com/python-hyper/h2/issues/1247")
    @coroutine_test
    async def test_connect_request(self, mockserver: MockServer) -> None:
        request = Request(
            mockserver.url("/file", is_secure=self.is_secure), method="CONNECT"
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b""

    @coroutine_test
    async def test_custom_content_length_good(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/contentlength", is_secure=self.is_secure))
        custom_content_length = str(len(request.body))
        request.headers["Content-Length"] = custom_content_length
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.text == custom_content_length

    @coroutine_test
    async def test_custom_content_length_bad(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        request = Request(mockserver.url("/contentlength", is_secure=self.is_secure))
        actual_content_length = str(len(request.body))
        bad_content_length = str(len(request.body) + 1)
        request.headers["Content-Length"] = bad_content_length
        async with self.get_dh() as download_handler:
            with caplog.at_level(logging.DEBUG):
                response = await download_handler.download_request(request)
        assert response.text == actual_content_length
        assert (
            "scrapy.core._http2.stream",
            logging.WARNING,
            f"Ignoring bad Content-Length header "
            f"{bad_content_length!r} of request {request}, sending "
            f"{actual_content_length!r} instead",
        ) in caplog.record_tuples

    @coroutine_test
    async def test_data_loss_handling(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/broken", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            with pytest.raises(DownloadFailedError):
                await download_handler.download_request(request)

    @coroutine_test
    async def test_download_405_data(self, mockserver: MockServer) -> None:
        """Servers without HTTP/2 support answer the connection preface with a
        405 status line, which this handler reports as a download failure
        instead of waiting for frames that never arrive."""
        request = Request(mockserver.url("/h2-no-support", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            with pytest.raises(DownloadFailedError, match="405 Method Not Allowed"):
                await download_handler.download_request(request)

    @coroutine_test
    async def test_download_plain_http(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/text"))
        async with self.get_dh() as download_handler:
            with pytest.raises(UnsupportedURLSchemeError):
                await download_handler.download_request(request)

    @coroutine_test
    async def test_download_proxy(self, mockserver: MockServer) -> None:
        request = Request(
            mockserver.url("/text", is_secure=self.is_secure),
            meta={"proxy": "https://example.com:8080"},
        )
        async with self.get_dh() as download_handler:
            with pytest.raises(NotImplementedError):
                await download_handler.download_request(request)

    @coroutine_test
    async def test_download_pushed_stream(self, mockserver: MockServer) -> None:
        """Pushed responses are ignored."""
        request = Request(mockserver.url("/h2-push", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"Works"


class TestSimpleHttp2(H2DownloadHandlerMixin, TestSimpleHttpsBase):
    pass


class TestHttp2WrongHostname(H2DownloadHandlerMixin, TestHttpsWrongHostnameBase):
    pass


class TestHttp2InvalidDNSId(H2DownloadHandlerMixin, TestHttpsInvalidDNSIdBase):
    pass


class TestHttp2InvalidDNSPattern(
    H2DownloadHandlerMixin, TestHttpsInvalidDNSPatternBase
):
    pass


class TestHttp2CustomCiphers(H2DownloadHandlerMixin, TestHttpsCustomCiphersBase):
    pass


class TestHttp2TLSVersion(H2DownloadHandlerMixin, TestHttpsTLSVersionBase):
    pass


class TestHttp2WithCrawler(H2DownloadHandlerMixin, TestHttpWithCrawlerBase):
    is_secure = True


@pytest.mark.skip(reason="Proxy support is not implemented yet")
class TestHttp2Proxy(H2DownloadHandlerMixin, TestHttpProxyBase):
    is_secure = True


@pytest.mark.skip(reason="Proxy support is not implemented yet")
@pytest.mark.requires_mitmproxy
class TestMitmProxy(H2DownloadHandlerMixin, TestMitmProxyBase):
    pass


@pytest.mark.requires_internet
class TestRealWebsite(H2DownloadHandlerMixin, TestRealWebsiteBase):
    @property
    def platform_cert_store_works(self) -> bool:
        return sys.platform != "win32"
