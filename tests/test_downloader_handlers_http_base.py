"""Base classes for HTTP download handler tests."""

from __future__ import annotations

import gzip
import json
import platform
import re
import sys
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from http import HTTPStatus
from ipaddress import IPv4Address
from socket import gethostbyname
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import urlparse

import pytest
from twisted.internet.ssl import Certificate
from twisted.python.failure import Failure

from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadCancelledError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadTimeoutError,
    ResponseDataLossError,
    ScrapyDeprecationWarning,
    StopDownload,
    UnsupportedURLSchemeError,
)
from scrapy.http import Headers, HtmlResponse, Request, Response, TextResponse
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests import NON_EXISTING_RESOLVABLE
from tests.mockserver.proxy_echo import ProxyEchoMockServer
from tests.mockserver.simple_https import SimpleMockServer
from tests.spiders import (
    BytesReceivedCallbackSpider,
    BytesReceivedErrbackSpider,
    HeadersReceivedCallbackSpider,
    HeadersReceivedErrbackSpider,
    SingleRequestSpider,
)
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from scrapy.core.downloader.handlers import DownloadHandlerProtocol
    from tests.mockserver.http import MockServer


class TestHttpBase(ABC):
    is_secure: bool = False
    http2: bool = False
    # whether the handler supports per-request bindaddress
    handler_supports_bindaddress_meta: bool = True
    # RFC 9113 §8.1.1 explicitly says that a Content-Length mismatch is a
    # stream error (of type PROTOCOL_ERROR) so the client will send
    # RST_STREAM. Some libraries do only this while e.g. h2 also closes the
    # connection (see handling of ProtocolError in
    # h2.connection.H2Connection.receive_data()), thus closing all streams that
    # were using it, and we handle this as a normal exception.
    handler_supports_http2_dataloss: bool = True
    # default headers added by the underlying library that cannot be suppressed
    always_present_req_headers: ClassVar[frozenset[str]] = frozenset()

    @property
    @abstractmethod
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        raise NotImplementedError

    @asynccontextmanager
    async def get_dh(
        self, settings_dict: dict[str, Any] | None = None
    ) -> AsyncGenerator[DownloadHandlerProtocol]:
        crawler = get_crawler(DefaultSpider, settings_dict)
        crawler.spider = crawler._create_spider()
        dh = build_from_crawler(self.download_handler_cls, crawler)
        try:
            yield dh
        finally:
            await dh.close()

    @coroutine_test
    async def test_unsupported_scheme(self) -> None:
        request = Request("unsupp://unsupported.scheme")
        async with self.get_dh() as download_handler:
            with pytest.raises(UnsupportedURLSchemeError):
                await download_handler.download_request(request)

    @coroutine_test
    async def test_download(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"Works"

    @coroutine_test
    async def test_download_head(self, mockserver: MockServer) -> None:
        request = Request(
            mockserver.url("/text", is_secure=self.is_secure), method="HEAD"
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b""

    @pytest.mark.parametrize(
        "http_status",
        [
            pytest.param(http_status, id=f"status={http_status.value}")
            for http_status in HTTPStatus
            if http_status.value == 200 or http_status.value // 100 in (4, 5)
        ],
    )
    @coroutine_test
    async def test_download_has_correct_http_status_code(
        self, mockserver: MockServer, http_status: HTTPStatus
    ) -> None:
        request = Request(
            mockserver.url(f"/status?n={http_status.value}", is_secure=self.is_secure)
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == http_status.value

    @coroutine_test
    async def test_server_receives_correct_request_headers(
        self, mockserver: MockServer
    ) -> None:
        request_headers = {
            # common request headers
            "Accept": "text/html",
            "Accept-Charset": "utf-8",
            "Accept-Datetime": "Thu, 31 May 2007 20:35:00 GMT",
            "Accept-Encoding": "gzip, deflate",
            # custom headers
            "X-Custom-Header": "Custom Value",
        }

        request = Request(
            mockserver.url("/echo", is_secure=self.is_secure),
            headers=request_headers,
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == HTTPStatus.OK
        body = json.loads(response.body.decode("utf-8"))
        assert "headers" in body
        for header_name, header_value in request_headers.items():
            assert header_name in body["headers"]
            assert body["headers"][header_name] == [header_value]

    @coroutine_test
    async def test_request_header_none(self, mockserver: MockServer) -> None:
        """Adding a header with None as the value should not send that header."""
        request_headers = {
            "Cookie": None,
            "X-Custom-Header": None,
        }
        request = Request(
            mockserver.url("/echo", is_secure=self.is_secure),
            headers=request_headers,
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == HTTPStatus.OK
        body = json.loads(response.body.decode("utf-8"))
        assert "headers" in body
        for header_name in request_headers:
            assert header_name not in body["headers"]

    @pytest.mark.parametrize(
        "request_headers",
        [
            {"X-Custom-Header": ["foo", "bar"]},
            [("X-Custom-Header", "foo"), ("X-Custom-Header", "bar")],
        ],
    )
    @coroutine_test
    async def test_request_header_duplicate(
        self, mockserver: MockServer, request_headers: Any
    ) -> None:
        """All values for a header should be sent."""
        request = Request(
            mockserver.url("/echo", is_secure=self.is_secure),
            headers=request_headers,
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == HTTPStatus.OK
        body = json.loads(response.body.decode("utf-8"))
        assert "headers" in body
        assert body["headers"]["X-Custom-Header"] == ["foo", "bar"]

    @coroutine_test
    async def test_server_receives_no_extra_headers(
        self, mockserver: MockServer
    ) -> None:
        """Test that the handler doesn't add headers to the request."""
        request = Request(mockserver.url("/echo", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == HTTPStatus.OK
        body = json.loads(response.body.decode("utf-8"))
        assert "headers" in body
        received_headers = set(body["headers"].keys())
        allowed_headers = {
            "Connection",
            "Content-Length",
            "Host",
        } | self.always_present_req_headers
        extra_headers = received_headers - allowed_headers
        assert not extra_headers, body["headers"]

    @coroutine_test
    async def test_server_receives_correct_request_body(
        self, mockserver: MockServer
    ) -> None:
        request_body = {
            "message": "It works!",
        }
        request = Request(
            mockserver.url("/echo", is_secure=self.is_secure),
            body=json.dumps(request_body),
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == HTTPStatus.OK
        body = json.loads(response.body.decode("utf-8"))
        assert json.loads(body["body"]) == request_body

    @coroutine_test
    async def test_download_has_correct_response_headers(
        self, mockserver: MockServer
    ) -> None:
        # these headers will be set on the response in the resource and returned
        response_headers = {
            # common response headers
            "Access-Control-Allow-Origin": "*",
            "Allow": "Get, Head",
            "Age": "12",
            "Cache-Control": "max-age=3600",
            "Content-Encoding": "gzip",
            "Content-MD5": "Q2hlY2sgSW50ZWdyaXR5IQ==",
            "Content-Type": "text/html; charset=utf-8",
            "Date": "Tue, 15 Nov 1994 08:12:31 GMT",
            "Pragma": "no-cache",
            "Retry-After": "120",
            "Set-Cookie": "CookieName=CookieValue; Max-Age=3600; Version=1",
            "WWW-Authenticate": "Basic",
            # custom headers
            "X-Custom-Header": "Custom Header Value",
        }

        request = Request(
            mockserver.url("/response-headers", is_secure=self.is_secure),
            headers={"content-type": "application/json"},
            body=json.dumps(response_headers),
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == 200
        for header_name, header_value in response_headers.items():
            assert header_name in response.headers, (
                f"Response was missing expected header {header_name}"
            )
            assert response.headers.getlist(header_name) == [
                header_value.encode(encoding="utf-8")
            ]

    @coroutine_test
    async def test_download_no_extra_response_headers(
        self, mockserver: MockServer
    ) -> None:
        """Test that the handler doesn't add headers to the response."""
        request = Request(
            mockserver.url("/response-headers", is_secure=self.is_secure),
            headers={"content-type": "application/json"},
            body=json.dumps({}),
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == 200
        received_headers = set(response.headers.keys())
        allowed_headers = {
            b"Content-Length",
            b"Content-Type",
            b"Date",
            b"Server",
        }
        extra_headers = received_headers - allowed_headers
        assert not extra_headers, response.headers

    @coroutine_test
    async def test_redirect_status(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/redirect", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == 302
        assert response.headers["Location"] == b"/redirected"

    @coroutine_test
    async def test_redirect_status_head(self, mockserver: MockServer) -> None:
        request = Request(
            mockserver.url("/redirect", is_secure=self.is_secure), method="HEAD"
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == 302
        assert response.headers["Location"] == b"/redirected"

    @coroutine_test
    async def test_timeout_download_from_spider_nodata_rcvd(
        self, mockserver: MockServer, reactor_pytest: str
    ) -> None:
        if reactor_pytest == "asyncio" and sys.platform == "win32":
            # https://twistedmatrix.com/trac/ticket/10279
            pytest.skip(
                "This test produces DirtyReactorAggregateError on Windows with asyncio"
            )

        # client connects but no data is received
        meta = {"download_timeout": 0.5}
        request = Request(mockserver.url("/wait", is_secure=self.is_secure), meta=meta)
        async with self.get_dh() as download_handler:
            d = deferred_from_coro(download_handler.download_request(request))
            with pytest.raises(DownloadTimeoutError):
                await maybe_deferred_to_future(d)

    @coroutine_test
    async def test_timeout_download_from_spider_server_hangs(
        self,
        mockserver: MockServer,
        reactor_pytest: str,
    ) -> None:
        if reactor_pytest == "asyncio" and sys.platform == "win32":
            # https://twistedmatrix.com/trac/ticket/10279
            pytest.skip(
                "This test produces DirtyReactorAggregateError on Windows with asyncio"
            )
        # client connects, server send headers and some body bytes but hangs
        meta = {"download_timeout": 0.5}
        request = Request(
            mockserver.url("/hang-after-headers", is_secure=self.is_secure), meta=meta
        )
        async with self.get_dh() as download_handler:
            d = deferred_from_coro(download_handler.download_request(request))
            with pytest.raises(DownloadTimeoutError):
                await maybe_deferred_to_future(d)

    @pytest.mark.parametrize("send_header", [True, False])
    @coroutine_test
    async def test_host_header(self, send_header: bool, mockserver: MockServer) -> None:
        host_port = f"{mockserver.host}:{mockserver.port(is_secure=self.is_secure)}"
        request = Request(
            mockserver.url("/host", is_secure=self.is_secure),
            headers={"Host": host_port} if send_header else {},
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == host_port.encode()
        if send_header:
            assert request.headers.get("Host") == host_port.encode()
        else:
            assert not request.headers

    @coroutine_test
    async def test_content_length_zero_bodyless_post_request_headers(
        self, mockserver: MockServer
    ) -> None:
        """Tests if "Content-Length: 0" is sent for bodyless POST requests.

        This is not strictly required by HTTP RFCs but can cause trouble
        for some web servers.
        See:
        https://github.com/scrapy/scrapy/issues/823
        https://issues.apache.org/jira/browse/TS-2902
        https://github.com/kennethreitz/requests/issues/405
        https://bugs.python.org/issue14721
        """
        request = Request(
            mockserver.url("/contentlength", is_secure=self.is_secure), method="POST"
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"0"

    @coroutine_test
    async def test_content_length_zero_bodyless_post_only_one(
        self, mockserver: MockServer
    ) -> None:
        request = Request(
            mockserver.url("/echo", is_secure=self.is_secure), method="POST"
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        headers = Headers(json.loads(response.text)["headers"])
        contentlengths = headers.getlist("Content-Length")
        assert len(contentlengths) == 1
        assert contentlengths == [b"0"]

    @coroutine_test
    async def test_payload(self, mockserver: MockServer) -> None:
        body = b"1" * 100  # PayloadResource requires body length to be 100
        request = Request(
            mockserver.url("/payload", is_secure=self.is_secure),
            method="POST",
            body=body,
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == body

    @coroutine_test
    async def test_response_header_content_length(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.headers[b"content-length"] == b"5"

    @pytest.mark.parametrize(
        ("filename", "body", "response_class"),
        [
            ("foo.html", b"", HtmlResponse),
            ("foo", b"<!DOCTYPE html>\n<title>.</title>", HtmlResponse),
        ],
    )
    @coroutine_test
    async def test_response_class(
        self,
        filename: str,
        body: bytes,
        response_class: type[Response],
        mockserver: MockServer,
    ) -> None:
        request = Request(
            mockserver.url(f"/{filename}", is_secure=self.is_secure), body=body
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert type(response) is response_class  # pylint: disable=unidiomatic-typecheck

    @coroutine_test
    async def test_get_duplicate_header(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/duplicate-header", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.headers.getlist(b"Set-Cookie") == [b"a=b", b"c=d"]

    @coroutine_test
    async def test_download_is_not_automatically_gzip_decoded(
        self, mockserver: MockServer
    ) -> None:
        """Test download handler does not automatically decode content using the scheme provided in Content-Encoding header"""

        data = "compress-me"

        # send a request to mock resource that gzip encodes the "data" url parameter
        request = Request(
            mockserver.url(f"/compress?data={data}", is_secure=self.is_secure),
            headers={
                "accept-encoding": "gzip",
            },
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)

        assert response.status == 200

        # check that the Content-Encoding header is gzip
        content_encoding = response.headers[b"Content-Encoding"]
        assert content_encoding == b"gzip"

        # check that the response is still encoded
        # by checking for the magic number that is always included at the start of a gzip encoding
        # see https://datatracker.ietf.org/doc/html/rfc1952#page-5 section 2.3.1
        GZIP_MAGIC = b"\x1f\x8b"
        assert response.body[:2] == GZIP_MAGIC, "Response body was not in gzip format"

        # check that a gzip decoding matches the data sent in the request
        expected_decoding = bytes(data, encoding="utf-8")
        assert gzip.decompress(response.body) == expected_decoding

    @coroutine_test
    async def test_no_cookie_processing_or_persistence(
        self, mockserver: MockServer
    ) -> None:
        cookie_name = "foo"
        cookie_value = "bar"

        # check that cookies are not modified
        request = Request(
            mockserver.url(
                f"/set-cookie?{cookie_name}={cookie_value}", is_secure=self.is_secure
            )
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
            assert response.status == 200
            set_cookie = response.headers.get(b"Set-Cookie")
            assert set_cookie == f"{cookie_name}={cookie_value}".encode()

            # check that cookies are not sent in the next request
            request = Request(mockserver.url("/echo", is_secure=self.is_secure))
            response = await download_handler.download_request(request)
            assert response.status == 200
            headers = Headers(json.loads(response.text)["headers"])
            assert "Cookie" not in headers
            assert "cookie" not in headers

    @coroutine_test
    async def test_download_latency(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            await download_handler.download_request(request)
        assert "download_latency" in request.meta
        latency = request.meta["download_latency"]
        if sys.version_info < (3, 13) and platform.system() == "Windows":
            # time.monotonic() resolution is too low here:
            # https://docs.python.org/3/whatsnew/3.13.html#time
            assert latency >= 0
        else:
            assert latency > 0

    @coroutine_test
    async def test_download_without_maxsize_limit(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"Works"

    @coroutine_test
    async def test_response_class_choosing_request(
        self, mockserver: MockServer
    ) -> None:
        """Tests choosing of correct response type
        in case of Content-Type is empty but body contains text.
        """
        body = b"Some plain text\ndata with tabs\t and null bytes\0"
        request = Request(
            mockserver.url("/nocontenttype", is_secure=self.is_secure), body=body
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert type(response) is TextResponse  # pylint: disable=unidiomatic-typecheck

    @coroutine_test
    async def test_download_with_maxsize(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))

        # 10 is minimal size for this request and the limit is only counted on
        # response body. (regardless of headers)
        async with self.get_dh({"DOWNLOAD_MAXSIZE": 5}) as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"Works"

        caplog.clear()
        msg = "Expected to receive 5 bytes which is larger than download max size (4)"
        async with self.get_dh({"DOWNLOAD_MAXSIZE": 4}) as download_handler:
            with pytest.raises(DownloadCancelledError, match=re.escape(msg)):
                await download_handler.download_request(request)
        assert msg in caplog.text

    @coroutine_test
    async def test_download_with_maxsize_very_large_file(
        self, mockserver: MockServer, caplog: pytest.LogCaptureFixture
    ) -> None:
        request = Request(mockserver.url("/largechunkedfile", is_secure=self.is_secure))
        async with self.get_dh({"DOWNLOAD_MAXSIZE": 1_500}) as download_handler:
            with pytest.raises(DownloadCancelledError):
                await download_handler.download_request(request)
        assert re.search(
            r"Received \d+ bytes which is larger than download max size \(1500\)",
            caplog.text,
        )

    @coroutine_test
    async def test_download_with_maxsize_per_req(self, mockserver: MockServer) -> None:
        meta = {"download_maxsize": 2}
        request = Request(mockserver.url("/text", is_secure=self.is_secure), meta=meta)
        async with self.get_dh() as download_handler:
            with pytest.raises(DownloadCancelledError):
                await download_handler.download_request(request)

    @coroutine_test
    async def test_download_with_small_maxsize_via_setting(
        self, mockserver: MockServer
    ) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        async with self.get_dh({"DOWNLOAD_MAXSIZE": 2}) as download_handler:
            with pytest.raises(DownloadCancelledError):
                await download_handler.download_request(request)

    @coroutine_test
    async def test_download_with_large_maxsize_via_setting(
        self, mockserver: MockServer
    ) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        async with self.get_dh({"DOWNLOAD_MAXSIZE": 100}) as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"Works"

    @coroutine_test
    async def test_download_with_warnsize(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        async with self.get_dh({"DOWNLOAD_WARNSIZE": 4}) as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"Works"
        assert (
            "Expected to receive 5 bytes which is larger than download warn size (4)"
            in caplog.text
        )

    @coroutine_test
    async def test_download_with_warnsize_no_content_length(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        request = Request(
            mockserver.url("/delay?n=0.1", is_secure=self.is_secure),
        )
        async with self.get_dh({"DOWNLOAD_WARNSIZE": 10}) as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"Response delayed for 0.100 seconds\n"
        assert (
            "Received 35 bytes which is larger than download warn size (10)"
            in caplog.text
        )

    @coroutine_test
    async def test_download_chunked_content(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/chunked", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"chunked content\n"

    @coroutine_test
    async def test_download_cause_data_loss(self, mockserver: MockServer) -> None:
        if self.http2 and not self.handler_supports_http2_dataloss:
            pytest.skip("This handler doesn't support dataloss on HTTP/2")
        request = Request(mockserver.url("/broken", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            with pytest.raises(ResponseDataLossError):
                await download_handler.download_request(request)

    @coroutine_test
    async def test_download_cause_data_loss_double_warning(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        if self.http2 and not self.handler_supports_http2_dataloss:
            pytest.skip("This handler doesn't support dataloss on HTTP/2")
        request = Request(mockserver.url("/broken", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            with pytest.raises(ResponseDataLossError):
                await download_handler.download_request(request)
            assert "Got data loss" in caplog.text
            caplog.clear()
            with pytest.raises(ResponseDataLossError):
                await download_handler.download_request(request)
            # no repeated warning
            assert "Got data loss" not in caplog.text

    @coroutine_test
    async def test_download_allow_data_loss_broken(
        self, mockserver: MockServer
    ) -> None:
        if self.http2 and not self.handler_supports_http2_dataloss:
            pytest.skip("This handler doesn't support dataloss on HTTP/2")
        request = Request(
            mockserver.url("/broken", is_secure=self.is_secure),
            meta={"download_fail_on_dataloss": False},
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.flags == ["dataloss"]
        assert response.text == "partial"

    @coroutine_test
    async def test_download_allow_data_loss_broken_chunked(
        self, mockserver: MockServer
    ) -> None:
        if self.http2:
            pytest.skip("Chunked encoding is specific to HTTP/1.1")
        request = Request(
            mockserver.url("/broken-chunked", is_secure=self.is_secure),
            meta={"download_fail_on_dataloss": False},
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.flags == ["dataloss"]
        assert response.text == "chunked content\n"

    @coroutine_test
    async def test_download_allow_data_loss_via_setting(
        self, mockserver: MockServer
    ) -> None:
        if self.http2 and not self.handler_supports_http2_dataloss:
            pytest.skip("This handler doesn't support dataloss on HTTP/2")
        request = Request(mockserver.url("/broken", is_secure=self.is_secure))
        async with self.get_dh(
            {"DOWNLOAD_FAIL_ON_DATALOSS": False}
        ) as download_handler:
            response = await download_handler.download_request(request)
        assert response.flags == ["dataloss"]

    @coroutine_test
    async def test_download_conn_failed(self) -> None:
        # copy of TestCrawl.test_retry_conn_failed()
        scheme = "https" if self.is_secure else "http"
        request = Request(f"{scheme}://localhost:65432/")
        async with self.get_dh() as download_handler:
            with pytest.raises(DownloadConnectionRefusedError):
                await download_handler.download_request(request)

    @coroutine_test
    async def test_download_conn_lost(self, mockserver: MockServer) -> None:
        # copy of TestCrawl.test_retry_conn_lost()
        request = Request(mockserver.url("/drop?abort=0", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            with pytest.raises(ResponseDataLossError):
                await download_handler.download_request(request)

    @coroutine_test
    async def test_download_conn_aborted(self, mockserver: MockServer) -> None:
        # copy of TestCrawl.test_retry_conn_aborted()
        if self.http2:
            # it may be possible to write a separate resource that does something
            # suitable on HTTP/2 without sending Content-Length
            pytest.skip(
                "On HTTP/2 this triggers a Content-Length mismatch error instead."
            )
        request = Request(mockserver.url("/drop?abort=1", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            with pytest.raises(DownloadFailedError):
                await download_handler.download_request(request)

    @pytest.mark.skipif(
        NON_EXISTING_RESOLVABLE, reason="Non-existing hosts are resolvable"
    )
    @coroutine_test
    async def test_download_dns_error(self) -> None:
        # copy of TestCrawl.test_retry_dns_error()
        scheme = "https" if self.is_secure else "http"
        request = Request(f"{scheme}://dns.resolution.invalid./")
        async with self.get_dh() as download_handler:
            with pytest.raises(CannotResolveHostError):
                await download_handler.download_request(request)

    @coroutine_test
    async def test_protocol(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/host", is_secure=self.is_secure))
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.protocol == "HTTP/1.1"

    @pytest.mark.skipif(
        sys.platform == "darwin",
        reason="127.0.0.2 is not available on macOS by default",
    )
    @pytest.mark.parametrize("setting_value", [("127.0.0.2", 0), "127.0.0.2"])
    @coroutine_test
    async def test_download_bind_address_setting(
        self, mockserver: MockServer, setting_value: Any
    ) -> None:
        request = Request(mockserver.url("/client-ip", is_secure=self.is_secure))
        async with self.get_dh(
            {"DOWNLOAD_BIND_ADDRESS": setting_value}
        ) as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"127.0.0.2"

    @pytest.mark.skipif(
        sys.platform == "darwin",
        reason="127.0.0.2 is not available on macOS by default",
    )
    @pytest.mark.parametrize("meta_value", [("127.0.0.2", 0), "127.0.0.2"])
    @coroutine_test
    async def test_download_bind_address_meta(
        self, mockserver: MockServer, caplog: pytest.LogCaptureFixture, meta_value: Any
    ) -> None:
        request = Request(
            mockserver.url("/client-ip", is_secure=self.is_secure),
            meta={"bindaddress": meta_value},
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        if self.handler_supports_bindaddress_meta:
            assert response.body == b"127.0.0.2"
        else:
            assert (
                "The 'bindaddress' request meta key is not supported by" in caplog.text
            )


class TestHttpsBase(TestHttpBase):
    is_secure = True

    tls_log_message = (
        'SSL connection certificate: issuer "/C=IE/O=Scrapy/CN=localhost", '
        'subject "/C=IE/O=Scrapy/CN=localhost"'
    )

    def test_download_conn_lost(self) -> None:  # type: ignore[override]
        # For some reason (maybe related to TLS shutdown flow, and maybe the
        # mockserver resource can be fixed so that this works) HTTPS clients
        # (not just Scrapy) hang on /drop?abort=0.
        pytest.skip("Unable to test on HTTPS")

    @coroutine_test
    async def test_tls_logging(
        self, mockserver: MockServer, caplog: pytest.LogCaptureFixture
    ) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        async with self.get_dh(
            {"DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING": True}
        ) as download_handler:
            with caplog.at_level("DEBUG"):
                response = await download_handler.download_request(request)
        assert response.body == b"Works"
        assert self.tls_log_message in caplog.text

    @coroutine_test
    async def test_verify_certs_deprecated(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        with (  # noqa: PT031
            pytest.warns(
                ScrapyDeprecationWarning,
                match="'DOWNLOADER_CLIENTCONTEXTFACTORY' setting is deprecated",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match="BrowserLikeContextFactory is deprecated",
            ),
        ):
            async with self.get_dh(
                {
                    "DOWNLOADER_CLIENTCONTEXTFACTORY": "scrapy.core.downloader.contextfactory.BrowserLikeContextFactory"
                }
            ) as download_handler:
                with pytest.raises(
                    (DownloadConnectionRefusedError, DownloadFailedError)
                ):
                    await download_handler.download_request(request)

    @coroutine_test
    async def test_verify_certs(self, mockserver: MockServer) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        async with self.get_dh(
            {"DOWNLOAD_VERIFY_CERTIFICATES": True}
        ) as download_handler:
            with pytest.raises((DownloadConnectionRefusedError, DownloadFailedError)):
                await download_handler.download_request(request)


class TestSimpleHttpsBase(ABC):
    """Base class for special cases tested with just one simple request"""

    keyfile = "keys/localhost.key"
    certfile = "keys/localhost.crt"
    host = "localhost"
    cipher_string: str | None = None

    @pytest.fixture(scope="class")
    def simple_mockserver(self) -> Generator[SimpleMockServer]:
        with SimpleMockServer(
            self.keyfile, self.certfile, self.cipher_string
        ) as simple_mockserver:
            yield simple_mockserver

    @pytest.fixture(scope="class")
    def url(self, simple_mockserver: SimpleMockServer) -> str:
        # need to use self.host instead of what mockserver returns
        return f"https://{self.host}:{simple_mockserver.port(is_secure=True)}/file"

    @property
    @abstractmethod
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        raise NotImplementedError

    @asynccontextmanager
    async def get_dh(self) -> AsyncGenerator[DownloadHandlerProtocol]:
        if self.cipher_string is not None:
            settings_dict = {"DOWNLOADER_CLIENT_TLS_CIPHERS": self.cipher_string}
        else:
            settings_dict = None
        crawler = get_crawler(DefaultSpider, settings_dict=settings_dict)
        crawler.spider = crawler._create_spider()
        dh = build_from_crawler(self.download_handler_cls, crawler)
        try:
            yield dh
        finally:
            await dh.close()

    @coroutine_test
    async def test_download(self, url: str) -> None:
        request = Request(url)
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.body == b"0123456789"


class TestHttpsWrongHostnameBase(TestSimpleHttpsBase):
    # above tests use a server certificate for "localhost",
    # client connection to "localhost" too.
    # here we test that even if the server certificate is for another domain,
    # "www.example.com" in this case,
    # the tests still pass
    keyfile = "keys/example-com.key.pem"
    certfile = "keys/example-com.cert.pem"


class TestHttpsInvalidDNSIdBase(TestSimpleHttpsBase):
    """Connect to HTTPS hosts with IP while certificate uses domain names IDs."""

    host = "127.0.0.1"


class TestHttpsInvalidDNSPatternBase(TestSimpleHttpsBase):
    """Connect to HTTPS hosts where the certificate are issued to an ip instead of a domain."""

    keyfile = "keys/localhost.ip.key"
    certfile = "keys/localhost.ip.crt"


class TestHttpsCustomCiphersBase(TestSimpleHttpsBase):
    cipher_string = "CAMELLIA256-SHA"


class TestHttpWithCrawlerBase(ABC):
    @property
    @abstractmethod
    def settings_dict(self) -> dict[str, Any] | None:
        raise NotImplementedError

    is_secure = False

    @coroutine_test
    async def test_download_with_content_length(self, mockserver: MockServer) -> None:
        crawler = get_crawler(SingleRequestSpider, self.settings_dict)
        # http://localhost:8998/partial set Content-Length to 1024, use download_maxsize= 1000 to avoid
        # download it
        await maybe_deferred_to_future(
            crawler.crawl(
                seed=Request(
                    url=mockserver.url("/partial", is_secure=self.is_secure),
                    meta={"download_maxsize": 1000},
                )
            )
        )
        assert crawler.spider
        failure = crawler.spider.meta["failure"]  # type: ignore[attr-defined]
        assert isinstance(failure.value, DownloadCancelledError)

    @coroutine_test
    async def test_download(self, mockserver: MockServer) -> None:
        crawler = get_crawler(SingleRequestSpider, self.settings_dict)
        await maybe_deferred_to_future(
            crawler.crawl(
                seed=Request(url=mockserver.url("", is_secure=self.is_secure))
            )
        )
        assert crawler.spider
        failure = crawler.spider.meta.get("failure")  # type: ignore[attr-defined]
        assert failure is None
        reason = crawler.spider.meta["close_reason"]  # type: ignore[attr-defined]
        assert reason == "finished"

    @coroutine_test
    async def test_response_ssl_certificate(self, mockserver: MockServer) -> None:
        if not self.is_secure:
            pytest.skip("Only applies to HTTPS")
        # copy of TestCrawl.test_response_ssl_certificate()
        # the current test implementation can only work for Twisted-based download handlers
        crawler = get_crawler(SingleRequestSpider, self.settings_dict)
        url = mockserver.url("/echo?body=test", is_secure=self.is_secure)
        await crawler.crawl_async(seed=url, mockserver=mockserver)
        assert isinstance(crawler.spider, SingleRequestSpider)
        cert = crawler.spider.meta["responses"][0].certificate
        assert isinstance(cert, Certificate)
        assert cert.getSubject().commonName == b"localhost"
        assert cert.getIssuer().commonName == b"localhost"

    @coroutine_test
    async def test_response_ip_address(self, mockserver: MockServer) -> None:
        # copy of TestCrawl.test_response_ip_address()
        crawler = get_crawler(SingleRequestSpider, self.settings_dict)
        url = mockserver.url("/echo?body=test", is_secure=self.is_secure)
        expected_netloc, _ = urlparse(url).netloc.split(":")
        await crawler.crawl_async(seed=url, mockserver=mockserver)
        assert isinstance(crawler.spider, SingleRequestSpider)
        ip_address = crawler.spider.meta["responses"][0].ip_address
        assert isinstance(ip_address, IPv4Address)
        assert str(ip_address) == gethostbyname(expected_netloc)

    @coroutine_test
    async def test_bytes_received_stop_download_callback(
        self, mockserver: MockServer
    ) -> None:
        # copy of TestCrawl.test_bytes_received_stop_download_callback()
        crawler = get_crawler(BytesReceivedCallbackSpider, self.settings_dict)
        await crawler.crawl_async(mockserver=mockserver, is_secure=self.is_secure)
        assert isinstance(crawler.spider, BytesReceivedCallbackSpider)
        assert crawler.spider.meta.get("failure") is None
        assert isinstance(crawler.spider.meta["response"], Response)
        assert crawler.spider.meta["response"].body == crawler.spider.meta.get(
            "bytes_received"
        )
        assert (
            len(crawler.spider.meta["response"].body)
            < crawler.spider.full_response_length
        )

    @coroutine_test
    async def test_bytes_received_stop_download_errback(
        self, mockserver: MockServer
    ) -> None:
        # copy of TestCrawl.test_bytes_received_stop_download_errback()
        crawler = get_crawler(BytesReceivedErrbackSpider, self.settings_dict)
        await crawler.crawl_async(mockserver=mockserver, is_secure=self.is_secure)
        assert isinstance(crawler.spider, BytesReceivedErrbackSpider)
        assert crawler.spider.meta.get("response") is None
        assert isinstance(crawler.spider.meta["failure"], Failure)
        assert isinstance(crawler.spider.meta["failure"].value, StopDownload)
        assert isinstance(crawler.spider.meta["failure"].value.response, Response)
        assert crawler.spider.meta[
            "failure"
        ].value.response.body == crawler.spider.meta.get("bytes_received")
        assert (
            len(crawler.spider.meta["failure"].value.response.body)
            < crawler.spider.full_response_length
        )

    @coroutine_test
    async def test_headers_received_stop_download_callback(
        self, mockserver: MockServer
    ) -> None:
        # copy of TestCrawl.test_headers_received_stop_download_callback()
        crawler = get_crawler(HeadersReceivedCallbackSpider, self.settings_dict)
        await crawler.crawl_async(mockserver=mockserver, is_secure=self.is_secure)
        assert isinstance(crawler.spider, HeadersReceivedCallbackSpider)
        assert crawler.spider.meta.get("failure") is None
        assert isinstance(crawler.spider.meta["response"], Response)
        assert crawler.spider.meta["response"].headers == crawler.spider.meta.get(
            "headers_received"
        )

    @coroutine_test
    async def test_headers_received_stop_download_errback(
        self, mockserver: MockServer
    ) -> None:
        # copy of TestCrawl.test_headers_received_stop_download_errback()
        crawler = get_crawler(HeadersReceivedErrbackSpider, self.settings_dict)
        await crawler.crawl_async(mockserver=mockserver, is_secure=self.is_secure)
        assert isinstance(crawler.spider, HeadersReceivedErrbackSpider)
        assert crawler.spider.meta.get("response") is None
        assert isinstance(crawler.spider.meta["failure"], Failure)
        assert isinstance(crawler.spider.meta["failure"].value, StopDownload)
        assert isinstance(crawler.spider.meta["failure"].value.response, Response)
        assert crawler.spider.meta[
            "failure"
        ].value.response.headers == crawler.spider.meta.get("headers_received")


class TestHttpProxyBase(ABC):
    is_secure = False
    expected_http_proxy_request_body = b"http://example.com"
    expected_http_proxy_quoted_request_body = b"http://example.com/list?%5B0%5D=a"
    expected_http_proxy_verbatim_request_body = b"http://example.com/list?[0]=a"

    @property
    @abstractmethod
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        raise NotImplementedError

    @pytest.fixture(scope="session")
    def proxy_mockserver(self) -> Generator[ProxyEchoMockServer]:
        with ProxyEchoMockServer() as proxy:
            yield proxy

    @asynccontextmanager
    async def get_dh(self) -> AsyncGenerator[DownloadHandlerProtocol]:
        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        dh = build_from_crawler(self.download_handler_cls, crawler)
        try:
            yield dh
        finally:
            await dh.close()

    @coroutine_test
    async def test_download_with_proxy(
        self, proxy_mockserver: ProxyEchoMockServer
    ) -> None:
        http_proxy = proxy_mockserver.url("", is_secure=self.is_secure)
        request = Request("http://example.com", meta={"proxy": http_proxy})
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == 200
        assert response.url == request.url
        assert response.body == self.expected_http_proxy_request_body

    @coroutine_test
    async def test_download_without_proxy(
        self, proxy_mockserver: ProxyEchoMockServer
    ) -> None:
        request = Request(
            proxy_mockserver.url("/path/to/resource", is_secure=self.is_secure)
        )
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == 200
        assert response.url == request.url
        assert response.body == b"/path/to/resource"

    @coroutine_test
    async def test_download_with_proxy_https_timeout(
        self, proxy_mockserver: ProxyEchoMockServer
    ) -> None:
        if NON_EXISTING_RESOLVABLE:
            pytest.skip("Non-existing hosts are resolvable")
        http_proxy = proxy_mockserver.url("", is_secure=self.is_secure)
        domain = "https://no-such-domain.nosuch"
        request = Request(domain, meta={"proxy": http_proxy, "download_timeout": 0.2})
        async with self.get_dh() as download_handler:
            with pytest.raises(DownloadTimeoutError) as exc_info:
                await download_handler.download_request(request)
        assert domain in str(exc_info.value)

    @coroutine_test
    async def test_download_with_proxy_without_http_scheme(
        self, proxy_mockserver: ProxyEchoMockServer
    ) -> None:
        http_proxy = f"{proxy_mockserver.host}:{proxy_mockserver.port()}"
        request = Request("http://example.com", meta={"proxy": http_proxy})
        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
        assert response.status == 200
        assert response.url == request.url
        assert response.body == self.expected_http_proxy_request_body

    @coroutine_test
    async def test_download_with_proxy_verbatim_url(
        self, proxy_mockserver: ProxyEchoMockServer
    ) -> None:
        http_proxy = proxy_mockserver.url("", is_secure=self.is_secure)
        url = "http://example.com/list?[0]=a"
        request = Request(url, meta={"proxy": http_proxy})
        request_verbatim = Request(
            url, meta={"proxy": http_proxy, "verbatim_url": True}
        )

        async with self.get_dh() as download_handler:
            response = await download_handler.download_request(request)
            response_verbatim = await download_handler.download_request(
                request_verbatim
            )

        assert response.status == 200
        assert response_verbatim.status == 200
        assert response.body == self.expected_http_proxy_quoted_request_body
        assert response_verbatim.body == self.expected_http_proxy_verbatim_request_body
