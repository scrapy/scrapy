"""Base classes for HTTP download handler tests."""

from __future__ import annotations

import gzip
import json
import sys
from abc import ABC, abstractmethod
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from pytest_twisted import async_yield_fixture
from testfixtures import LogCapture
from twisted.internet import defer, error
from twisted.web._newclient import ResponseFailed
from twisted.web.http import _DataLoss

from scrapy.http import Headers, HtmlResponse, Request, Response, TextResponse
from scrapy.spiders import Spider
from scrapy.utils.asyncio import call_later
from scrapy.utils.defer import (
    deferred_f_from_coro_f,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests import NON_EXISTING_RESOLVABLE
from tests.mockserver.proxy_echo import ProxyEchoMockServer
from tests.mockserver.simple_https import SimpleMockServer
from tests.spiders import SingleRequestSpider

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from scrapy.core.downloader.handlers import DownloadHandlerProtocol
    from tests.mockserver.http import MockServer


async def download_request(
    download_handler: DownloadHandlerProtocol,
    request: Request,
    spider: Spider = DefaultSpider(),
) -> Response:
    return await maybe_deferred_to_future(
        download_handler.download_request(request, spider)
    )


async def close_dh(dh: DownloadHandlerProtocol) -> None:
    # needed because the interface of close() is not clearly defined
    if not hasattr(dh, "close"):
        return
    c = dh.close()
    if c is None:
        return
    # covers coroutines and Deferreds; won't work if close() uses Futures inside
    await c


class TestHttpBase(ABC):
    is_secure = False

    @property
    @abstractmethod
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        raise NotImplementedError

    @async_yield_fixture
    async def download_handler(self) -> AsyncGenerator[DownloadHandlerProtocol]:
        dh = build_from_crawler(self.download_handler_cls, get_crawler())

        yield dh

        await close_dh(dh)

    @deferred_f_from_coro_f
    async def test_download(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        response = await download_request(download_handler, request)
        assert response.body == b"Works"

    @deferred_f_from_coro_f
    async def test_download_head(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(
            mockserver.url("/text", is_secure=self.is_secure), method="HEAD"
        )
        response = await download_request(download_handler, request)
        assert response.body == b""

    @pytest.mark.parametrize(
        "http_status",
        [
            pytest.param(http_status, id=f"status={http_status.value}")
            for http_status in HTTPStatus
            if http_status.value == 200 or http_status.value // 100 in (4, 5)
        ],
    )
    @deferred_f_from_coro_f
    async def test_download_has_correct_http_status_code(
        self,
        mockserver: MockServer,
        download_handler: DownloadHandlerProtocol,
        http_status: HTTPStatus,
    ) -> None:
        request = Request(
            mockserver.url(f"/status?n={http_status.value}", is_secure=self.is_secure)
        )
        response = await download_request(download_handler, request)
        assert response.status == http_status.value

    @deferred_f_from_coro_f
    async def test_server_receives_correct_request_headers(
        self,
        mockserver: MockServer,
        download_handler: DownloadHandlerProtocol,
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
        response = await download_request(download_handler, request)
        assert response.status == HTTPStatus.OK
        body = json.loads(response.body.decode("utf-8"))
        assert "headers" in body
        for header_name, header_value in request_headers.items():
            assert header_name in body["headers"]
            assert body["headers"][header_name] == [header_value]

    @deferred_f_from_coro_f
    async def test_server_receives_correct_request_body(
        self,
        mockserver: MockServer,
        download_handler: DownloadHandlerProtocol,
    ) -> None:
        request_body = {
            "message": "It works!",
        }
        request = Request(
            mockserver.url("/echo", is_secure=self.is_secure),
            body=json.dumps(request_body),
        )
        response = await download_request(download_handler, request)
        assert response.status == HTTPStatus.OK
        body = json.loads(response.body.decode("utf-8"))
        assert json.loads(body["body"]) == request_body

    @deferred_f_from_coro_f
    async def test_download_has_correct_response_headers(
        self,
        mockserver: MockServer,
        download_handler: DownloadHandlerProtocol,
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
            "Date": "Date: Tue, 15 Nov 1994 08:12:31 GMT",
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
        response = await download_request(download_handler, request)
        assert response.status == 200
        for header_name, header_value in response_headers.items():
            assert header_name in response.headers, (
                f"Response was missing expected header {header_name}"
            )
            assert response.headers[header_name] == bytes(
                header_value, encoding="utf-8"
            )

    @deferred_f_from_coro_f
    async def test_redirect_status(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(mockserver.url("/redirect", is_secure=self.is_secure))
        response = await download_request(download_handler, request)
        assert response.status == 302

    @deferred_f_from_coro_f
    async def test_redirect_status_head(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(
            mockserver.url("/redirect", is_secure=self.is_secure), method="HEAD"
        )
        response = await download_request(download_handler, request)
        assert response.status == 302

    @deferred_f_from_coro_f
    async def test_timeout_download_from_spider_nodata_rcvd(
        self,
        mockserver: MockServer,
        download_handler: DownloadHandlerProtocol,
        reactor_pytest: str,
    ) -> None:
        if reactor_pytest == "asyncio" and sys.platform == "win32":
            # https://twistedmatrix.com/trac/ticket/10279
            pytest.skip(
                "This test produces DirtyReactorAggregateError on Windows with asyncio"
            )

        # client connects but no data is received
        meta = {"download_timeout": 0.5}
        request = Request(mockserver.url("/wait", is_secure=self.is_secure), meta=meta)
        d = deferred_from_coro(download_request(download_handler, request))
        with pytest.raises((defer.TimeoutError, error.TimeoutError)):
            await maybe_deferred_to_future(d)

    @deferred_f_from_coro_f
    async def test_timeout_download_from_spider_server_hangs(
        self,
        mockserver: MockServer,
        download_handler: DownloadHandlerProtocol,
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
        d = deferred_from_coro(download_request(download_handler, request))
        with pytest.raises((defer.TimeoutError, error.TimeoutError)):
            await maybe_deferred_to_future(d)

    @pytest.mark.parametrize("send_header", [True, False])
    @deferred_f_from_coro_f
    async def test_host_header(
        self,
        send_header: bool,
        mockserver: MockServer,
        download_handler: DownloadHandlerProtocol,
    ) -> None:
        host_port = f"{mockserver.host}:{mockserver.port(is_secure=self.is_secure)}"
        request = Request(
            mockserver.url("/host", is_secure=self.is_secure),
            headers={"Host": host_port} if send_header else {},
        )
        response = await download_request(download_handler, request)
        assert response.body == host_port.encode()
        if send_header:
            assert request.headers.get("Host") == host_port.encode()
        else:
            assert not request.headers

    @deferred_f_from_coro_f
    async def test_content_length_zero_bodyless_post_request_headers(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
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
        response = await download_request(download_handler, request)
        assert response.body == b"0"

    @deferred_f_from_coro_f
    async def test_content_length_zero_bodyless_post_only_one(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(
            mockserver.url("/echo", is_secure=self.is_secure), method="POST"
        )
        response = await download_request(download_handler, request)
        headers = Headers(json.loads(response.text)["headers"])
        contentlengths = headers.getlist("Content-Length")
        assert len(contentlengths) == 1
        assert contentlengths == [b"0"]

    @deferred_f_from_coro_f
    async def test_payload(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        body = b"1" * 100  # PayloadResource requires body length to be 100
        request = Request(
            mockserver.url("/payload", is_secure=self.is_secure),
            method="POST",
            body=body,
        )
        response = await download_request(download_handler, request)
        assert response.body == body

    @deferred_f_from_coro_f
    async def test_response_header_content_length(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(
            mockserver.url("/text", is_secure=self.is_secure), method="GET"
        )
        response = await download_request(download_handler, request)
        assert response.headers[b"content-length"] == b"5"

    @pytest.mark.parametrize(
        ("filename", "body", "response_class"),
        [
            ("foo.html", b"", HtmlResponse),
            ("foo", b"<!DOCTYPE html>\n<title>.</title>", HtmlResponse),
        ],
    )
    @deferred_f_from_coro_f
    async def test_response_class(
        self,
        filename: str,
        body: bytes,
        response_class: type[Response],
        mockserver: MockServer,
        download_handler: DownloadHandlerProtocol,
    ) -> None:
        request = Request(
            mockserver.url(f"/{filename}", is_secure=self.is_secure), body=body
        )
        response = await download_request(download_handler, request)
        assert type(response) is response_class  # pylint: disable=unidiomatic-typecheck

    @deferred_f_from_coro_f
    async def test_get_duplicate_header(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(mockserver.url("/duplicate-header", is_secure=self.is_secure))
        response = await download_request(download_handler, request)
        assert response.headers.getlist(b"Set-Cookie") == [b"a=b", b"c=d"]

    @deferred_f_from_coro_f
    async def test_download_is_not_automatically_gzip_decoded(
        self, download_handler: DownloadHandlerProtocol, mockserver: MockServer
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
        response = await download_request(download_handler, request)

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

    @deferred_f_from_coro_f
    async def test_no_cookie_processing_or_persistence(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        cookie_name = "foo"
        cookie_value = "bar"

        # check that cookies are not modified
        request = Request(
            mockserver.url(
                f"/set-cookie?{cookie_name}={cookie_value}", is_secure=self.is_secure
            )
        )
        response = await download_request(download_handler, request)
        assert response.status == 200
        set_cookie = response.headers.get(b"Set-Cookie")
        assert set_cookie == f"{cookie_name}={cookie_value}".encode()

        # check that cookies are not sent in the next request
        request = Request(mockserver.url("/echo", is_secure=self.is_secure))
        response = await download_request(download_handler, request)
        assert response.status == 200
        headers = Headers(json.loads(response.text)["headers"])
        assert "Cookie" not in headers
        assert "cookie" not in headers


class TestHttp11Base(TestHttpBase):
    """HTTP 1.1 test case"""

    @deferred_f_from_coro_f
    async def test_download_without_maxsize_limit(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        response = await download_request(download_handler, request)
        assert response.body == b"Works"

    @deferred_f_from_coro_f
    async def test_response_class_choosing_request(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        """Tests choosing of correct response type
        in case of Content-Type is empty but body contains text.
        """
        body = b"Some plain text\ndata with tabs\t and null bytes\0"
        request = Request(
            mockserver.url("/nocontenttype", is_secure=self.is_secure), body=body
        )
        response = await download_request(download_handler, request)
        assert type(response) is TextResponse  # pylint: disable=unidiomatic-typecheck

    @deferred_f_from_coro_f
    async def test_download_with_maxsize(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))

        # 10 is minimal size for this request and the limit is only counted on
        # response body. (regardless of headers)
        response = await download_request(
            download_handler, request, Spider("foo", download_maxsize=5)
        )
        assert response.body == b"Works"

        with pytest.raises((defer.CancelledError, error.ConnectionAborted)):
            await download_request(
                download_handler, request, Spider("foo", download_maxsize=4)
            )

    @deferred_f_from_coro_f
    async def test_download_with_maxsize_very_large_file(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        # TODO: the logger check is specific to scrapy.core.downloader.handlers.http11
        with mock.patch("scrapy.core.downloader.handlers.http11.logger") as logger:
            request = Request(
                mockserver.url("/largechunkedfile", is_secure=self.is_secure)
            )

            def check(logger: mock.Mock) -> None:
                logger.warning.assert_called_once_with(mock.ANY, mock.ANY)

            with pytest.raises((defer.CancelledError, error.ConnectionAborted)):
                await download_request(
                    download_handler, request, Spider("foo", download_maxsize=1500)
                )

            # As the error message is logged in the dataReceived callback, we
            # have to give a bit of time to the reactor to process the queue
            # after closing the connection.
            d: defer.Deferred[mock.Mock] = defer.Deferred()
            d.addCallback(check)
            call_later(0.1, d.callback, logger)
            await maybe_deferred_to_future(d)

    @deferred_f_from_coro_f
    async def test_download_with_maxsize_per_req(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        meta = {"download_maxsize": 2}
        request = Request(mockserver.url("/text", is_secure=self.is_secure), meta=meta)
        with pytest.raises((defer.CancelledError, error.ConnectionAborted)):
            await download_request(download_handler, request)

    @deferred_f_from_coro_f
    async def test_download_with_small_maxsize_per_spider(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        with pytest.raises((defer.CancelledError, error.ConnectionAborted)):
            await download_request(
                download_handler, request, Spider("foo", download_maxsize=2)
            )

    @deferred_f_from_coro_f
    async def test_download_with_large_maxsize_per_spider(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(mockserver.url("/text", is_secure=self.is_secure))
        response = await download_request(
            download_handler, request, Spider("foo", download_maxsize=100)
        )
        assert response.body == b"Works"

    @deferred_f_from_coro_f
    async def test_download_chunked_content(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(mockserver.url("/chunked", is_secure=self.is_secure))
        response = await download_request(download_handler, request)
        assert response.body == b"chunked content\n"

    @pytest.mark.parametrize("url", ["broken", "broken-chunked"])
    @deferred_f_from_coro_f
    async def test_download_cause_data_loss(
        self,
        url: str,
        mockserver: MockServer,
        download_handler: DownloadHandlerProtocol,
    ) -> None:
        # TODO: this one checks for Twisted-specific exceptions
        request = Request(mockserver.url(f"/{url}", is_secure=self.is_secure))
        with pytest.raises(ResponseFailed) as exc_info:
            await download_request(download_handler, request)
        assert any(r.check(_DataLoss) for r in exc_info.value.reasons)

    @pytest.mark.parametrize("url", ["broken", "broken-chunked"])
    @deferred_f_from_coro_f
    async def test_download_allow_data_loss(
        self,
        url: str,
        mockserver: MockServer,
        download_handler: DownloadHandlerProtocol,
    ) -> None:
        request = Request(
            mockserver.url(f"/{url}", is_secure=self.is_secure),
            meta={"download_fail_on_dataloss": False},
        )
        response = await download_request(download_handler, request)
        assert response.flags == ["dataloss"]

    @pytest.mark.parametrize("url", ["broken", "broken-chunked"])
    @deferred_f_from_coro_f
    async def test_download_allow_data_loss_via_setting(
        self, url: str, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(settings_dict={"DOWNLOAD_FAIL_ON_DATALOSS": False})
        download_handler = build_from_crawler(self.download_handler_cls, crawler)
        request = Request(mockserver.url(f"/{url}", is_secure=self.is_secure))
        try:
            response = await maybe_deferred_to_future(
                download_handler.download_request(request, DefaultSpider())
            )
        finally:
            d = download_handler.close()  # type: ignore[attr-defined]
            if d is not None:
                await maybe_deferred_to_future(d)
        assert response.flags == ["dataloss"]

    @deferred_f_from_coro_f
    async def test_protocol(
        self, mockserver: MockServer, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(
            mockserver.url("/host", is_secure=self.is_secure), method="GET"
        )
        response = await download_request(download_handler, request)
        assert response.protocol == "HTTP/1.1"


class TestHttps11Base(TestHttp11Base):
    is_secure = True

    tls_log_message = (
        'SSL connection certificate: issuer "/C=IE/O=Scrapy/CN=localhost", '
        'subject "/C=IE/O=Scrapy/CN=localhost"'
    )

    @deferred_f_from_coro_f
    async def test_tls_logging(self, mockserver: MockServer) -> None:
        crawler = get_crawler(
            settings_dict={"DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING": True}
        )
        download_handler = build_from_crawler(self.download_handler_cls, crawler)
        try:
            with LogCapture() as log_capture:
                request = Request(mockserver.url("/text", is_secure=self.is_secure))
                response = await maybe_deferred_to_future(
                    download_handler.download_request(request, DefaultSpider())
                )
                assert response.body == b"Works"
                log_capture.check_present(
                    ("scrapy.core.downloader.tls", "DEBUG", self.tls_log_message)
                )
        finally:
            d = download_handler.close()  # type: ignore[attr-defined]
            if d is not None:
                await maybe_deferred_to_future(d)


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

    @async_yield_fixture
    async def download_handler(self) -> AsyncGenerator[DownloadHandlerProtocol]:
        if self.cipher_string is not None:
            settings_dict = {"DOWNLOADER_CLIENT_TLS_CIPHERS": self.cipher_string}
        else:
            settings_dict = None
        crawler = get_crawler(settings_dict=settings_dict)
        dh = build_from_crawler(self.download_handler_cls, crawler)

        yield dh

        await close_dh(dh)

    @deferred_f_from_coro_f
    async def test_download(
        self, url: str, download_handler: DownloadHandlerProtocol
    ) -> None:
        request = Request(url)
        response = await download_request(download_handler, request)
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

    @deferred_f_from_coro_f
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
        assert isinstance(failure.value, defer.CancelledError)

    @deferred_f_from_coro_f
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


class TestHttpProxyBase(ABC):
    is_secure = False
    expected_http_proxy_request_body = b"http://example.com"

    @property
    @abstractmethod
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        raise NotImplementedError

    @pytest.fixture(scope="session")
    def proxy_mockserver(self) -> Generator[ProxyEchoMockServer]:
        with ProxyEchoMockServer() as proxy:
            yield proxy

    @async_yield_fixture
    async def download_handler(self) -> AsyncGenerator[DownloadHandlerProtocol]:
        dh = build_from_crawler(self.download_handler_cls, get_crawler())

        yield dh

        await close_dh(dh)

    @deferred_f_from_coro_f
    async def test_download_with_proxy(
        self,
        proxy_mockserver: ProxyEchoMockServer,
        download_handler: DownloadHandlerProtocol,
    ) -> None:
        http_proxy = proxy_mockserver.url("", is_secure=self.is_secure)
        request = Request("http://example.com", meta={"proxy": http_proxy})
        response = await download_request(download_handler, request)
        assert response.status == 200
        assert response.url == request.url
        assert response.body == self.expected_http_proxy_request_body

    @deferred_f_from_coro_f
    async def test_download_without_proxy(
        self,
        proxy_mockserver: ProxyEchoMockServer,
        download_handler: DownloadHandlerProtocol,
    ) -> None:
        request = Request(
            proxy_mockserver.url("/path/to/resource", is_secure=self.is_secure)
        )
        response = await download_request(download_handler, request)
        assert response.status == 200
        assert response.url == request.url
        assert response.body == b"/path/to/resource"

    @deferred_f_from_coro_f
    async def test_download_with_proxy_https_timeout(
        self,
        proxy_mockserver: ProxyEchoMockServer,
        download_handler: DownloadHandlerProtocol,
    ) -> None:
        if NON_EXISTING_RESOLVABLE:
            pytest.skip("Non-existing hosts are resolvable")
        http_proxy = proxy_mockserver.url("", is_secure=self.is_secure)
        domain = "https://no-such-domain.nosuch"
        request = Request(domain, meta={"proxy": http_proxy, "download_timeout": 0.2})
        with pytest.raises(error.TimeoutError) as exc_info:
            await download_request(download_handler, request)
        assert domain in exc_info.value.osError

    @deferred_f_from_coro_f
    async def test_download_with_proxy_without_http_scheme(
        self,
        proxy_mockserver: ProxyEchoMockServer,
        download_handler: DownloadHandlerProtocol,
    ) -> None:
        http_proxy = f"{proxy_mockserver.host}:{proxy_mockserver.port()}"
        request = Request("http://example.com", meta={"proxy": http_proxy})
        response = await download_request(download_handler, request)
        assert response.status == 200
        assert response.url == request.url
        assert response.body == self.expected_http_proxy_request_body
