"""Tests for scrapy.core.downloader.handlers.http2.H2DownloadHandler."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from pytest_twisted import async_yield_fixture
from testfixtures import LogCapture
from twisted.internet import defer, error
from twisted.web import server
from twisted.web.error import SchemeNotSupported
from twisted.web.http import H2_ENABLED

from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from tests.mockserver import ssl_context_factory
from tests.test_downloader_handlers_http_base import (
    TestHttpMockServerBase,
    TestHttpProxyBase,
    TestHttps11Base,
    TestHttpsCustomCiphersBase,
    TestHttpsInvalidDNSIdBase,
    TestHttpsInvalidDNSPatternBase,
    TestHttpsWrongHostnameBase,
    UriResource,
    download_request,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from scrapy.core.downloader.handlers import DownloadHandlerProtocol


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
        self, server_port: int, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(self.getURL(server_port, "host"), method="GET")
        response = await download_request(download_handler, request)
        assert response.protocol == "h2"

    @deferred_f_from_coro_f
    async def test_download_with_maxsize_very_large_file(
        self, server_port: int, download_handler: DownloadHandlerProtocol
    ) -> None:
        from twisted.internet import reactor

        with mock.patch("scrapy.core.http2.stream.logger") as logger:
            request = Request(self.getURL(server_port, "largechunkedfile"))

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
        self, server_port: int, download_handler: DownloadHandlerProtocol
    ) -> None:
        request1 = Request(self.getURL(server_port, "file"))
        response1 = await download_request(download_handler, request1)
        assert response1.body == b"0123456789"

        request2 = Request(self.getURL(server_port, "echo"), method="POST")
        response2 = await download_request(download_handler, request2)
        assert response2.headers["Content-Length"] == b"79"

    @pytest.mark.xfail(reason="https://github.com/python-hyper/h2/issues/1247")
    @deferred_f_from_coro_f
    async def test_connect_request(
        self, server_port: int, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(self.getURL(server_port, "file"), method="CONNECT")
        response = await download_request(download_handler, request)
        assert response.body == b""

    @deferred_f_from_coro_f
    async def test_custom_content_length_good(
        self, server_port: int, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(self.getURL(server_port, "contentlength"))
        custom_content_length = str(len(request.body))
        request.headers["Content-Length"] = custom_content_length
        response = await download_request(download_handler, request)
        assert response.text == custom_content_length

    @deferred_f_from_coro_f
    async def test_custom_content_length_bad(
        self, server_port: int, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(self.getURL(server_port, "contentlength"))
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
        self, server_port: int, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(self.getURL(server_port, "echo"))
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


class TestHttp2MockServer(TestHttpMockServerBase):
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
    # only used for HTTPS tests
    keyfile = "keys/localhost.key"
    certfile = "keys/localhost.crt"
    scheme = "https"
    expected_http_proxy_request_body = b"/"

    @async_yield_fixture
    async def server_port(self) -> AsyncGenerator[int]:
        from twisted.internet import reactor

        site = server.Site(UriResource(), timeout=None)
        port = reactor.listenSSL(
            0,
            site,
            ssl_context_factory(self.keyfile, self.certfile),
            interface=self.host,
        )

        yield port.getHost().port

        await port.stopListening()

    @deferred_f_from_coro_f
    async def test_download_with_proxy_https_timeout(
        self, server_port: int, download_handler: DownloadHandlerProtocol
    ) -> None:
        with pytest.raises(NotImplementedError):
            await maybe_deferred_to_future(
                super().test_download_with_proxy_https_timeout(
                    server_port, download_handler
                )
            )
