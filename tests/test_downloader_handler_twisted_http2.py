"""Tests for scrapy.core.downloader.handlers.http2.H2DownloadHandler."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from testfixtures import LogCapture
from twisted.internet import defer, error
from twisted.web.error import SchemeNotSupported
from twisted.web.http import H2_ENABLED

from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from tests.test_downloader_handlers_http_base import (
    TestHttpProxyBase,
    TestHttps11Base,
    TestHttpsCustomCiphersBase,
    TestHttpsInvalidDNSIdBase,
    TestHttpsInvalidDNSPatternBase,
    TestHttpsWrongHostnameBase,
    TestHttpWithCrawlerBase,
    download_request,
)

if TYPE_CHECKING:
    from scrapy.core.downloader.handlers import DownloadHandlerProtocol
    from tests.mockserver.http import MockServer
    from tests.mockserver.proxy_echo import ProxyEchoMockServer


pytestmark = pytest.mark.skipif(
    not H2_ENABLED, reason="HTTP/2 support in Twisted is not enabled"
)


class H2DownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        # the import can fail when H2_ENABLED is False
        from scrapy.core.downloader.handlers.http2 import (  # noqa: PLC0415
            H2DownloadHandler,
        )

        return H2DownloadHandler


class TestHttps2(H2DownloadHandlerMixin, TestHttps11Base):
    HTTP2_DATALOSS_SKIP_REASON = "Content-Length mismatch raises InvalidBodyLengthError"

    @deferred_f_from_coro_f
    async def test_protocol(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(
            mockserver.url("/host", is_secure=self.is_secure), method="GET"
        )
        response = await download_request(download_handler, request)
        assert response.protocol == "h2"

    @deferred_f_from_coro_f
    async def test_download_with_maxsize_very_large_file(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        from twisted.internet import reactor

        with mock.patch("scrapy.core.http2.stream.logger") as logger:
            request = Request(
                mockserver.url("/largechunkedfile", is_secure=self.is_secure)
            )

            def check(logger: mock.Mock) -> None:
                logger.error.assert_called_once_with(mock.ANY)

            with pytest.raises((defer.CancelledError, error.ConnectionAborted)):
                await download_request(
                    download_handler, request, Spider("foo", download_maxsize=1500)
                )

            # As the error message is logged in the dataReceived callback, we
            # have to give a bit of time to the reactor to process the queue
            # after closing the connection.
            d: defer.Deferred[mock.Mock] = defer.Deferred()
            d.addCallback(check)
            reactor.callLater(0.1, d.callback, logger)
            await maybe_deferred_to_future(d)

    @deferred_f_from_coro_f
    async def test_unsupported_scheme(
        self, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request("ftp://unsupported.scheme")
        with pytest.raises(SchemeNotSupported):
            await download_request(download_handler, request)

    def test_download_cause_data_loss(self) -> None:  # type: ignore[override]
        pytest.skip(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_allow_data_loss(self) -> None:  # type: ignore[override]
        pytest.skip(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_allow_data_loss_via_setting(self) -> None:  # type: ignore[override]
        pytest.skip(self.HTTP2_DATALOSS_SKIP_REASON)

    @deferred_f_from_coro_f
    async def test_concurrent_requests_same_domain(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request1 = Request(mockserver.url("/text", is_secure=self.is_secure))
        response1 = await download_request(download_handler, request1)
        assert response1.body == b"Works"

        request2 = Request(
            mockserver.url("/echo", is_secure=self.is_secure), method="POST"
        )
        response2 = await download_request(download_handler, request2)
        assert response2.headers["Content-Length"] == b"79"

    @pytest.mark.xfail(reason="https://github.com/python-hyper/h2/issues/1247")
    @deferred_f_from_coro_f
    async def test_connect_request(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(
            mockserver.url("/file", is_secure=self.is_secure), method="CONNECT"
        )
        response = await download_request(download_handler, request)
        assert response.body == b""

    @deferred_f_from_coro_f
    async def test_custom_content_length_good(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(mockserver.url("/contentlength", is_secure=self.is_secure))
        custom_content_length = str(len(request.body))
        request.headers["Content-Length"] = custom_content_length
        response = await download_request(download_handler, request)
        assert response.text == custom_content_length

    @deferred_f_from_coro_f
    async def test_custom_content_length_bad(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(mockserver.url("/contentlength", is_secure=self.is_secure))
        actual_content_length = str(len(request.body))
        bad_content_length = str(len(request.body) + 1)
        request.headers["Content-Length"] = bad_content_length
        with LogCapture() as log:
            response = await download_request(download_handler, request)
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

    @deferred_f_from_coro_f
    async def test_duplicate_header(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(mockserver.url("/echo", is_secure=self.is_secure))
        header, value1, value2 = "Custom-Header", "foo", "bar"
        request.headers.appendlist(header, value1)
        request.headers.appendlist(header, value2)
        response = await download_request(download_handler, request)
        assert json.loads(response.text)["headers"][header] == [value1, value2]


class TestHttps2WrongHostname(H2DownloadHandlerMixin, TestHttpsWrongHostnameBase):
    pass


class TestHttps2InvalidDNSId(H2DownloadHandlerMixin, TestHttpsInvalidDNSIdBase):
    pass


class TestHttps2InvalidDNSPattern(
    H2DownloadHandlerMixin, TestHttpsInvalidDNSPatternBase
):
    pass


class TestHttps2CustomCiphers(H2DownloadHandlerMixin, TestHttpsCustomCiphersBase):
    pass


class TestHttp2WithCrawler(TestHttpWithCrawlerBase):
    """HTTP 2.0 test case with MockServer"""

    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return {
            "DOWNLOAD_HANDLERS": {
                "https": "scrapy.core.downloader.handlers.http2.H2DownloadHandler"
            }
        }

    is_secure = True


class TestHttps2Proxy(H2DownloadHandlerMixin, TestHttpProxyBase):
    is_secure = True
    expected_http_proxy_request_body = b"/"

    @deferred_f_from_coro_f
    async def test_download_with_proxy_https_timeout(
        self,
        proxy_mockserver: ProxyEchoMockServer,
        download_handler: DownloadHandlerProtocol,
    ) -> None:
        with pytest.raises(NotImplementedError):
            await maybe_deferred_to_future(
                super().test_download_with_proxy_https_timeout(
                    proxy_mockserver, download_handler
                )
            )

    @deferred_f_from_coro_f
    async def test_download_with_proxy_without_http_scheme(
        self,
        proxy_mockserver: ProxyEchoMockServer,
        download_handler: DownloadHandlerProtocol,
    ) -> None:
        with pytest.raises(SchemeNotSupported):
            await maybe_deferred_to_future(
                super().test_download_with_proxy_without_http_scheme(
                    proxy_mockserver, download_handler
                )
            )
