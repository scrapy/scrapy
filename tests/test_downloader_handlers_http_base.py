"""Base classes for HTTP download handler tests."""

from __future__ import annotations

import json
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import mkdtemp
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from testfixtures import LogCapture
from twisted.internet import defer, error
from twisted.internet.defer import inlineCallbacks, maybeDeferred
from twisted.protocols.policies import WrappingFactory
from twisted.trial import unittest
from twisted.web import resource, server, static, util
from twisted.web._newclient import ResponseFailed
from twisted.web.http import _DataLoss

from scrapy.http import Headers, HtmlResponse, Request, Response, TextResponse
from scrapy.spiders import Spider
from scrapy.utils.defer import (
    deferred_f_from_coro_f,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.python import to_bytes
from scrapy.utils.test import get_crawler
from tests import NON_EXISTING_RESOLVABLE
from tests.mockserver import (
    Echo,
    ForeverTakingResource,
    HostHeaderResource,
    MockServer,
    NoLengthResource,
    PayloadResource,
    ssl_context_factory,
)
from tests.spiders import SingleRequestSpider

if TYPE_CHECKING:
    from scrapy.core.downloader.handlers import DownloadHandlerProtocol


class ContentLengthHeaderResource(resource.Resource):
    """
    A testing resource which renders itself as the value of the Content-Length
    header from the request.
    """

    def render(self, request):
        return request.requestHeaders.getRawHeaders(b"content-length")[0]


class ChunkedResource(resource.Resource):
    def render(self, request):
        from twisted.internet import reactor

        def response():
            request.write(b"chunked ")
            request.write(b"content\n")
            request.finish()

        reactor.callLater(0, response)
        return server.NOT_DONE_YET


class BrokenChunkedResource(resource.Resource):
    def render(self, request):
        from twisted.internet import reactor

        def response():
            request.write(b"chunked ")
            request.write(b"content\n")
            # Disable terminating chunk on finish.
            request.chunked = False
            closeConnection(request)

        reactor.callLater(0, response)
        return server.NOT_DONE_YET


class BrokenDownloadResource(resource.Resource):
    def render(self, request):
        from twisted.internet import reactor

        def response():
            request.setHeader(b"Content-Length", b"20")
            request.write(b"partial")
            closeConnection(request)

        reactor.callLater(0, response)
        return server.NOT_DONE_YET


def closeConnection(request):
    # We have to force a disconnection for HTTP/1.1 clients. Otherwise
    # client keeps the connection open waiting for more data.
    request.channel.loseConnection()
    request.finish()


class EmptyContentTypeHeaderResource(resource.Resource):
    """
    A testing resource which renders itself as the value of request body
    without content-type header in response.
    """

    def render(self, request):
        request.setHeader("content-type", "")
        return request.content.read()


class LargeChunkedFileResource(resource.Resource):
    def render(self, request):
        from twisted.internet import reactor

        def response():
            for i in range(1024):
                request.write(b"x" * 1024)
            request.finish()

        reactor.callLater(0, response)
        return server.NOT_DONE_YET


class DuplicateHeaderResource(resource.Resource):
    def render(self, request):
        request.responseHeaders.setRawHeaders(b"Set-Cookie", [b"a=b", b"c=d"])
        return b""


class TestHttpBase(unittest.TestCase, ABC):
    scheme = "http"

    # only used for HTTPS tests
    keyfile = "keys/localhost.key"
    certfile = "keys/localhost.crt"

    @property
    @abstractmethod
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        raise NotImplementedError

    def setUp(self):
        from twisted.internet import reactor

        self.tmpname = Path(mkdtemp())
        (self.tmpname / "file").write_bytes(b"0123456789")
        r = static.File(str(self.tmpname))
        r.putChild(b"redirect", util.Redirect(b"/file"))
        r.putChild(b"wait", ForeverTakingResource())
        r.putChild(b"hang-after-headers", ForeverTakingResource(write=True))
        r.putChild(b"nolength", NoLengthResource())
        r.putChild(b"host", HostHeaderResource())
        r.putChild(b"payload", PayloadResource())
        r.putChild(b"broken", BrokenDownloadResource())
        r.putChild(b"chunked", ChunkedResource())
        r.putChild(b"broken-chunked", BrokenChunkedResource())
        r.putChild(b"contentlength", ContentLengthHeaderResource())
        r.putChild(b"nocontenttype", EmptyContentTypeHeaderResource())
        r.putChild(b"largechunkedfile", LargeChunkedFileResource())
        r.putChild(b"duplicate-header", DuplicateHeaderResource())
        r.putChild(b"echo", Echo())
        self.site = server.Site(r, timeout=None)
        self.wrapper = WrappingFactory(self.site)
        self.host = "localhost"
        if self.scheme == "https":
            # Using WrappingFactory do not enable HTTP/2 failing all the
            # tests with H2DownloadHandler
            self.port = reactor.listenSSL(
                0,
                self.site,
                ssl_context_factory(self.keyfile, self.certfile),
                interface=self.host,
            )
        else:
            self.port = reactor.listenTCP(0, self.wrapper, interface=self.host)
        self.portno = self.port.getHost().port
        self.download_handler = build_from_crawler(
            self.download_handler_cls, get_crawler()
        )

    @inlineCallbacks
    def tearDown(self):
        yield self.port.stopListening()
        if hasattr(self.download_handler, "close"):
            yield self.download_handler.close()
        shutil.rmtree(self.tmpname)

    def getURL(self, path):
        return f"{self.scheme}://{self.host}:{self.portno}/{path}"

    async def download_request(self, request: Request, spider: Spider) -> Response:
        return await maybe_deferred_to_future(
            self.download_handler.download_request(request, spider)
        )

    @deferred_f_from_coro_f
    async def test_download(self):
        request = Request(self.getURL("file"))
        response = await self.download_request(request, Spider("foo"))
        assert response.body == b"0123456789"

    @deferred_f_from_coro_f
    async def test_download_head(self):
        request = Request(self.getURL("file"), method="HEAD")
        response = await self.download_request(request, Spider("foo"))
        assert response.body == b""

    @deferred_f_from_coro_f
    async def test_redirect_status(self):
        request = Request(self.getURL("redirect"))
        response = await self.download_request(request, Spider("foo"))
        assert response.status == 302

    @deferred_f_from_coro_f
    async def test_redirect_status_head(self):
        request = Request(self.getURL("redirect"), method="HEAD")
        response = await self.download_request(request, Spider("foo"))
        assert response.status == 302

    @deferred_f_from_coro_f
    async def test_timeout_download_from_spider_nodata_rcvd(self):
        if self.reactor_pytest != "default" and sys.platform == "win32":
            # https://twistedmatrix.com/trac/ticket/10279
            pytest.skip(
                "This test produces DirtyReactorAggregateError on Windows with asyncio"
            )

        # client connects but no data is received
        spider = Spider("foo")
        meta = {"download_timeout": 0.5}
        request = Request(self.getURL("wait"), meta=meta)
        d = deferred_from_coro(self.download_request(request, spider))
        with pytest.raises((defer.TimeoutError, error.TimeoutError)):
            await maybe_deferred_to_future(d)

    @deferred_f_from_coro_f
    async def test_timeout_download_from_spider_server_hangs(self):
        if self.reactor_pytest != "default" and sys.platform == "win32":
            # https://twistedmatrix.com/trac/ticket/10279
            pytest.skip(
                "This test produces DirtyReactorAggregateError on Windows with asyncio"
            )
        # client connects, server send headers and some body bytes but hangs
        spider = Spider("foo")
        meta = {"download_timeout": 0.5}
        request = Request(self.getURL("hang-after-headers"), meta=meta)
        d = deferred_from_coro(self.download_request(request, spider))
        with pytest.raises((defer.TimeoutError, error.TimeoutError)):
            await maybe_deferred_to_future(d)

    @deferred_f_from_coro_f
    async def test_host_header_not_in_request_headers(self):
        request = Request(self.getURL("host"))
        response = await self.download_request(request, Spider("foo"))
        assert response.body == to_bytes(f"{self.host}:{self.portno}")
        assert not request.headers

    @deferred_f_from_coro_f
    async def test_host_header_set_in_request_headers(self):
        host = self.host + ":" + str(self.portno)
        request = Request(self.getURL("host"), headers={"Host": host})
        response = await self.download_request(request, Spider("foo"))
        assert response.body == host.encode()
        assert request.headers.get("Host") == host.encode()

    @deferred_f_from_coro_f
    async def test_content_length_zero_bodyless_post_request_headers(self):
        """Tests if "Content-Length: 0" is sent for bodyless POST requests.

        This is not strictly required by HTTP RFCs but can cause trouble
        for some web servers.
        See:
        https://github.com/scrapy/scrapy/issues/823
        https://issues.apache.org/jira/browse/TS-2902
        https://github.com/kennethreitz/requests/issues/405
        https://bugs.python.org/issue14721
        """
        request = Request(self.getURL("contentlength"), method="POST")
        response = await self.download_request(request, Spider("foo"))
        assert response.body == b"0"

    @deferred_f_from_coro_f
    async def test_content_length_zero_bodyless_post_only_one(self):
        request = Request(self.getURL("echo"), method="POST")
        response = await self.download_request(request, Spider("foo"))
        headers = Headers(json.loads(response.text)["headers"])
        contentlengths = headers.getlist("Content-Length")
        assert len(contentlengths) == 1
        assert contentlengths == [b"0"]

    @deferred_f_from_coro_f
    async def test_payload(self):
        body = b"1" * 100  # PayloadResource requires body length to be 100
        request = Request(self.getURL("payload"), method="POST", body=body)
        response = await self.download_request(request, Spider("foo"))
        assert response.body == body

    @deferred_f_from_coro_f
    async def test_response_header_content_length(self):
        request = Request(self.getURL("file"), method=b"GET")
        response = await self.download_request(request, Spider("foo"))
        assert response.headers[b"content-length"] == b"159"

    async def _test_response_class(
        self, filename: str, body: bytes, response_class: type[Response]
    ) -> None:
        request = Request(self.getURL(filename), body=body)
        response = await self.download_request(request, Spider("foo"))
        assert type(response) is response_class  # pylint: disable=unidiomatic-typecheck

    @deferred_f_from_coro_f
    async def test_response_class_from_url(self):
        await self._test_response_class("foo.html", b"", HtmlResponse)

    @deferred_f_from_coro_f
    async def test_response_class_from_body(self):
        await self._test_response_class(
            "foo",
            b"<!DOCTYPE html>\n<title>.</title>",
            HtmlResponse,
        )

    @deferred_f_from_coro_f
    async def test_get_duplicate_header(self):
        request = Request(self.getURL("duplicate-header"))
        response = await self.download_request(request, Spider("foo"))
        assert response.headers.getlist(b"Set-Cookie") == [b"a=b", b"c=d"]


class TestHttp11Base(TestHttpBase):
    """HTTP 1.1 test case"""

    @deferred_f_from_coro_f
    async def test_download_without_maxsize_limit(self):
        request = Request(self.getURL("file"))
        response = await self.download_request(request, Spider("foo"))
        assert response.body == b"0123456789"

    @deferred_f_from_coro_f
    async def test_response_class_choosing_request(self):
        """Tests choosing of correct response type
        in case of Content-Type is empty but body contains text.
        """
        body = b"Some plain text\ndata with tabs\t and null bytes\0"
        request = Request(self.getURL("nocontenttype"), body=body)
        response = await self.download_request(request, Spider("foo"))
        assert type(response) is TextResponse  # pylint: disable=unidiomatic-typecheck

    @deferred_f_from_coro_f
    async def test_download_with_maxsize(self):
        request = Request(self.getURL("file"))

        # 10 is minimal size for this request and the limit is only counted on
        # response body. (regardless of headers)
        response = await self.download_request(
            request, Spider("foo", download_maxsize=10)
        )
        assert response.body == b"0123456789"

        with pytest.raises((defer.CancelledError, error.ConnectionAborted)):
            await self.download_request(request, Spider("foo", download_maxsize=9))

    @deferred_f_from_coro_f
    async def test_download_with_maxsize_very_large_file(self):
        from twisted.internet import reactor

        # TODO: the logger check is specific to scrapy.core.downloader.handlers.http11
        with mock.patch("scrapy.core.downloader.handlers.http11.logger") as logger:
            request = Request(self.getURL("largechunkedfile"))

            def check(logger):
                logger.warning.assert_called_once_with(mock.ANY, mock.ANY)

            with pytest.raises((defer.CancelledError, error.ConnectionAborted)):
                await self.download_request(
                    request, Spider("foo", download_maxsize=1500)
                )

            # As the error message is logged in the dataReceived callback, we
            # have to give a bit of time to the reactor to process the queue
            # after closing the connection.
            d = defer.Deferred()
            d.addCallback(check)
            reactor.callLater(0.1, d.callback, logger)
            await maybe_deferred_to_future(d)

    @deferred_f_from_coro_f
    async def test_download_with_maxsize_per_req(self):
        meta = {"download_maxsize": 2}
        request = Request(self.getURL("file"), meta=meta)
        with pytest.raises((defer.CancelledError, error.ConnectionAborted)):
            await self.download_request(request, Spider("foo"))

    @deferred_f_from_coro_f
    async def test_download_with_small_maxsize_per_spider(self):
        request = Request(self.getURL("file"))
        with pytest.raises((defer.CancelledError, error.ConnectionAborted)):
            await self.download_request(request, Spider("foo", download_maxsize=2))

    @deferred_f_from_coro_f
    async def test_download_with_large_maxsize_per_spider(self):
        request = Request(self.getURL("file"))
        response = await self.download_request(
            request, Spider("foo", download_maxsize=100)
        )
        assert response.body == b"0123456789"

    @deferred_f_from_coro_f
    async def test_download_chunked_content(self):
        request = Request(self.getURL("chunked"))
        response = await self.download_request(request, Spider("foo"))
        assert response.body == b"chunked content\n"

    @deferred_f_from_coro_f
    async def test_download_broken_content_cause_data_loss(
        self, url: str = "broken"
    ) -> None:
        # TODO: this one checks for Twisted-specific exceptions
        request = Request(self.getURL(url))
        with pytest.raises(ResponseFailed) as exc_info:
            await self.download_request(request, Spider("foo"))
        assert any(r.check(_DataLoss) for r in exc_info.value.reasons)

    def test_download_broken_chunked_content_cause_data_loss(self):
        return self.test_download_broken_content_cause_data_loss("broken-chunked")

    @deferred_f_from_coro_f
    async def test_download_broken_content_allow_data_loss(
        self, url: str = "broken"
    ) -> None:
        request = Request(self.getURL(url), meta={"download_fail_on_dataloss": False})
        response = await self.download_request(request, Spider("foo"))
        assert response.flags == ["dataloss"]

    def test_download_broken_chunked_content_allow_data_loss(self):
        return self.test_download_broken_content_allow_data_loss("broken-chunked")

    @deferred_f_from_coro_f
    async def test_download_broken_content_allow_data_loss_via_setting(
        self, url: str = "broken"
    ) -> None:
        crawler = get_crawler(settings_dict={"DOWNLOAD_FAIL_ON_DATALOSS": False})
        download_handler = build_from_crawler(self.download_handler_cls, crawler)
        request = Request(self.getURL(url))
        response = await maybe_deferred_to_future(
            download_handler.download_request(request, Spider("foo"))
        )
        assert response.flags == ["dataloss"]

    def test_download_broken_chunked_content_allow_data_loss_via_setting(self):
        return self.test_download_broken_content_allow_data_loss_via_setting(
            "broken-chunked"
        )

    @deferred_f_from_coro_f
    async def test_protocol(self):
        request = Request(self.getURL("host"), method="GET")
        response = await self.download_request(request, Spider("foo"))
        assert response.protocol == "HTTP/1.1"


class TestHttps11Base(TestHttp11Base):
    scheme = "https"

    tls_log_message = (
        'SSL connection certificate: issuer "/C=IE/O=Scrapy/CN=localhost", '
        'subject "/C=IE/O=Scrapy/CN=localhost"'
    )

    @deferred_f_from_coro_f
    async def test_tls_logging(self):
        crawler = get_crawler(
            settings_dict={"DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING": True}
        )
        download_handler = build_from_crawler(self.download_handler_cls, crawler)
        try:
            with LogCapture() as log_capture:
                request = Request(self.getURL("file"))
                response = await maybe_deferred_to_future(
                    download_handler.download_request(request, Spider("foo"))
                )
                assert response.body == b"0123456789"
                log_capture.check_present(
                    ("scrapy.core.downloader.tls", "DEBUG", self.tls_log_message)
                )
        finally:
            await maybe_deferred_to_future(maybeDeferred(download_handler.close))


class TestSimpleHttpsBase(unittest.TestCase, ABC):
    """Base class for special cases tested with just one simple request"""

    keyfile = "keys/localhost.key"
    certfile = "keys/localhost.crt"
    cipher_string: str | None = None

    @property
    @abstractmethod
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        raise NotImplementedError

    def setUp(self):
        from twisted.internet import reactor

        self.tmpname = Path(mkdtemp())
        (self.tmpname / "file").write_bytes(b"0123456789")
        r = static.File(str(self.tmpname))
        self.site = server.Site(r, timeout=None)
        self.host = "localhost"
        self.port = reactor.listenSSL(
            0,
            self.site,
            ssl_context_factory(
                self.keyfile, self.certfile, cipher_string=self.cipher_string
            ),
            interface=self.host,
        )
        self.portno = self.port.getHost().port
        if self.cipher_string is not None:
            settings_dict = {"DOWNLOADER_CLIENT_TLS_CIPHERS": self.cipher_string}
        else:
            settings_dict = None
        crawler = get_crawler(settings_dict=settings_dict)
        self.download_handler = build_from_crawler(self.download_handler_cls, crawler)

    @inlineCallbacks
    def tearDown(self):
        yield self.port.stopListening()
        if hasattr(self.download_handler, "close"):
            yield self.download_handler.close()
        shutil.rmtree(self.tmpname)

    def getURL(self, path):
        return f"https://{self.host}:{self.portno}/{path}"

    async def download_request(self, request: Request, spider: Spider) -> Response:
        return await maybe_deferred_to_future(
            self.download_handler.download_request(request, spider)
        )

    @deferred_f_from_coro_f
    async def test_download(self):
        request = Request(self.getURL("file"))
        response = await self.download_request(request, Spider("foo"))
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

    def setUp(self):
        super().setUp()
        self.host = "127.0.0.1"


class TestHttpsInvalidDNSPatternBase(TestSimpleHttpsBase):
    """Connect to HTTPS hosts where the certificate are issued to an ip instead of a domain."""

    keyfile = "keys/localhost.ip.key"
    certfile = "keys/localhost.ip.crt"


class TestHttpsCustomCiphersBase(TestSimpleHttpsBase):
    cipher_string = "CAMELLIA256-SHA"


class TestHttpMockServerBase(unittest.TestCase, ABC):
    """HTTP 1.1 test case with MockServer"""

    @property
    @abstractmethod
    def settings_dict(self) -> dict[str, Any] | None:
        raise NotImplementedError

    is_secure = False

    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    @deferred_f_from_coro_f
    async def test_download_with_content_length(self):
        crawler = get_crawler(SingleRequestSpider, self.settings_dict)
        # http://localhost:8998/partial set Content-Length to 1024, use download_maxsize= 1000 to avoid
        # download it
        await maybe_deferred_to_future(
            crawler.crawl(
                seed=Request(
                    url=self.mockserver.url("/partial", is_secure=self.is_secure),
                    meta={"download_maxsize": 1000},
                )
            )
        )
        failure = crawler.spider.meta["failure"]
        assert isinstance(failure.value, defer.CancelledError)

    @deferred_f_from_coro_f
    async def test_download(self):
        crawler = get_crawler(SingleRequestSpider, self.settings_dict)
        await maybe_deferred_to_future(
            crawler.crawl(
                seed=Request(url=self.mockserver.url("", is_secure=self.is_secure))
            )
        )
        failure = crawler.spider.meta.get("failure")
        assert failure is None
        reason = crawler.spider.meta["close_reason"]
        assert reason == "finished"


class UriResource(resource.Resource):
    """Return the full uri that was requested"""

    def getChild(self, path, request):
        return self

    def render(self, request):
        # Note: this is an ugly hack for CONNECT request timeout test.
        #       Returning some data here fail SSL/TLS handshake
        # ToDo: implement proper HTTPS proxy tests, not faking them.
        if request.method != b"CONNECT":
            return request.uri
        return b""


class TestHttpProxyBase(unittest.TestCase, ABC):
    expected_http_proxy_request_body = b"http://example.com"

    @property
    @abstractmethod
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        raise NotImplementedError

    def setUp(self):
        from twisted.internet import reactor

        site = server.Site(UriResource(), timeout=None)
        wrapper = WrappingFactory(site)
        self.port = reactor.listenTCP(0, wrapper, interface="127.0.0.1")
        self.portno = self.port.getHost().port
        self.download_handler = build_from_crawler(
            self.download_handler_cls, get_crawler()
        )

    @inlineCallbacks
    def tearDown(self):
        yield self.port.stopListening()
        if hasattr(self.download_handler, "close"):
            yield self.download_handler.close()

    def getURL(self, path):
        return f"http://127.0.0.1:{self.portno}/{path}"

    async def download_request(self, request: Request, spider: Spider) -> Response:
        return await maybe_deferred_to_future(
            self.download_handler.download_request(request, spider)
        )

    @deferred_f_from_coro_f
    async def test_download_with_proxy(self):
        http_proxy = self.getURL("")
        request = Request("http://example.com", meta={"proxy": http_proxy})
        response = await self.download_request(request, Spider("foo"))
        assert response.status == 200
        assert response.url == request.url
        assert response.body == self.expected_http_proxy_request_body

    @deferred_f_from_coro_f
    async def test_download_without_proxy(self):
        request = Request(self.getURL("path/to/resource"))
        response = await self.download_request(request, Spider("foo"))
        assert response.status == 200
        assert response.url == request.url
        assert response.body == b"/path/to/resource"

    @deferred_f_from_coro_f
    async def test_download_with_proxy_https_timeout(self):
        if NON_EXISTING_RESOLVABLE:
            pytest.skip("Non-existing hosts are resolvable")
        http_proxy = self.getURL("")
        domain = "https://no-such-domain.nosuch"
        request = Request(domain, meta={"proxy": http_proxy, "download_timeout": 0.2})
        with pytest.raises(error.TimeoutError) as exc_info:
            await self.download_request(request, Spider("foo"))
        assert domain in exc_info.value.osError

    @deferred_f_from_coro_f
    async def test_download_with_proxy_without_http_scheme(self):
        http_proxy = self.getURL("").replace("http://", "")
        request = Request("http://example.com", meta={"proxy": http_proxy})
        response = await self.download_request(request, Spider("foo"))
        assert response.status == 200
        assert response.url == request.url
        assert response.body == self.expected_http_proxy_request_body
