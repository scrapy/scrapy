"""Tests for scrapy.core.downloader.handlers.http2.H2DownloadHandler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from testfixtures import LogCapture
from twisted.web.http import H2_ENABLED

from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import (
    DownloadFailedError,
    NotConfigured,
    UnsupportedURLSchemeError,
)
from scrapy.http import Request
from scrapy.utils.defer import maybe_deferred_to_future
from tests.test_downloader_handlers_http_base import (
    TestHttpProxyBase,
    TestHttpsBase,
    TestHttpsCustomCiphersBase,
    TestHttpsInvalidDNSIdBase,
    TestHttpsInvalidDNSPatternBase,
    TestHttpsWrongHostnameBase,
    TestHttpWithCrawlerBase,
)
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy.core.downloader.handlers import DownloadHandlerProtocol
    from tests.mockserver.http import MockServer
    from tests.mockserver.proxy_echo import ProxyEchoMockServer


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


def test_not_configured_without_reactor() -> None:
    from scrapy.core.downloader.handlers.http2 import H2DownloadHandler  # noqa: PLC0415

    crawler = Crawler(Spider, {"TWISTED_REACTOR_ENABLED": False})
    with pytest.raises(NotConfigured):
        H2DownloadHandler.from_crawler(crawler)


class TestHttp2(H2DownloadHandlerMixin, TestHttpsBase):
    http2 = True
    handler_supports_http2_dataloss = False

    @coroutine_test
    async def test_protocol(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/host", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.protocol == "h2"

    def test_download_conn_failed(self) -> None:  # type: ignore[override]
        # Unlike HTTP11DownloadHandler which raises it from download_request()
        # (without any special handling), here ConnectionRefusedError (raised in
        # twisted.internet.endpoints.startConnectionAttempts()) bubbles up as
        # an unhandled exception in a Deferred and the handler waits until
        # DOWNLOAD_TIMEOUT.
        pytest.skip("The handler doesn't properly reraise ConnectionRefusedError")

    def test_download_dns_error(self) -> None:  # type: ignore[override]
        # Unlike HTTP11DownloadHandler which raises it from download_request()
        # (without any special handling), here DNSLookupError (raised in
        # twisted.internet.endpoints.startConnectionAttempts()) bubbles up as
        # an unhandled exception in a Deferred and the handler waits until
        # DOWNLOAD_TIMEOUT.
        pytest.skip("The handler doesn't properly reraise DNSLookupError")

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
    async def test_custom_content_length_bad(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/contentlength", is_secure=self.is_secure))
        actual_content_length = str(len(request.body))
        bad_content_length = str(len(request.body) + 1)
        request.headers["Content-Length"] = bad_content_length
        async with self.get_dh() as download_handler:
            with LogCapture() as log:
                response = await download_handler.download_request(request)
        assert response.text == actual_content_length
        log.check_present(
            (
                "scrapy.core.http2.stream",
                "WARNING",
                f"Ignoring bad Content-Length header "
                f"{bad_content_length!r} of request {request}, sending "
                f"{actual_content_length!r} instead",
            )
        )

    @coroutine_test
    async def test_data_loss_handling(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/broken", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            with pytest.raises(DownloadFailedError):
                await download_handler.download_request(request)


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


class TestHttp2WithCrawler(TestHttpWithCrawlerBase):
    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return {
            "DOWNLOAD_HANDLERS": {
                "http": None,
                "https": "scrapy.core.downloader.handlers.http2.H2DownloadHandler",
            }
        }

    is_secure = True

    def test_bytes_received_stop_download_callback(self) -> None:  # type: ignore[override]
        pytest.skip("bytes_received support is not implemented")

    def test_bytes_received_stop_download_errback(self) -> None:  # type: ignore[override]
        pytest.skip("bytes_received support is not implemented")

    def test_headers_received_stop_download_callback(self) -> None:  # type: ignore[override]
        pytest.skip("headers_received support is not implemented")

    def test_headers_received_stop_download_errback(self) -> None:  # type: ignore[override]
        pytest.skip("headers_received support is not implemented")


class TestHttp2Proxy(H2DownloadHandlerMixin, TestHttpProxyBase):
    is_secure = True
    expected_http_proxy_request_body = b"/"
    expected_http_proxy_quoted_request_body = b"/list?%5B0%5D=a"
    expected_http_proxy_verbatim_request_body = b"/list?[0]=a"

    @coroutine_test
    async def test_download_with_proxy_https_timeout(
        self, proxy_mockserver: ProxyEchoMockServer
    ) -> None:
        with pytest.raises(NotImplementedError):
            await maybe_deferred_to_future(
                super().test_download_with_proxy_https_timeout(proxy_mockserver)  # type: ignore[arg-type]
            )

    @coroutine_test
    async def test_download_with_proxy_without_http_scheme(
        self, proxy_mockserver: ProxyEchoMockServer
    ) -> None:
        with pytest.raises(UnsupportedURLSchemeError):
            await maybe_deferred_to_future(
                super().test_download_with_proxy_without_http_scheme(proxy_mockserver)  # type: ignore[arg-type]
            )
