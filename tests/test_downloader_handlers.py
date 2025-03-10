from __future__ import annotations

import contextlib
import os
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import mkdtemp, mkstemp
from unittest import SkipTest, mock

import pytest
from testfixtures import LogCapture
from twisted.cred import checkers, credentials, portal
from twisted.internet import defer, error, reactor
from twisted.protocols.ftp import FTPFactory, FTPRealm
from twisted.protocols.policies import WrappingFactory
from twisted.trial import unittest
from twisted.web import resource, server, static, util
from twisted.web.client import ResponseFailed
from twisted.web.http import _DataLoss
from w3lib.url import path_to_file_uri

from scrapy.core.downloader.handlers import DownloadHandlerProtocol, DownloadHandlers
from scrapy.core.downloader.handlers.datauri import DataURIDownloadHandler
from scrapy.core.downloader.handlers.file import FileDownloadHandler
from scrapy.core.downloader.handlers.ftp import FTPDownloadHandler
from scrapy.core.downloader.handlers.http10 import HTTP10DownloadHandler
from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.core.downloader.handlers.s3 import S3DownloadHandler
from scrapy.exceptions import NotConfigured
from scrapy.http import Headers, HtmlResponse, Request
from scrapy.http.response.text import TextResponse
from scrapy.responsetypes import responsetypes
from scrapy.spiders import Spider
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


class DummyDH:
    lazy = False


class DummyLazyDH:
    # Default is lazy for backward compatibility
    pass


class OffDH:
    lazy = False

    def __init__(self, crawler):
        raise NotConfigured

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)


class TestLoad:
    def test_enabled_handler(self):
        handlers = {"scheme": DummyDH}
        crawler = get_crawler(settings_dict={"DOWNLOAD_HANDLERS": handlers})
        dh = DownloadHandlers(crawler)
        assert "scheme" in dh._schemes
        assert "scheme" in dh._handlers
        assert "scheme" not in dh._notconfigured

    def test_not_configured_handler(self):
        handlers = {"scheme": OffDH}
        crawler = get_crawler(settings_dict={"DOWNLOAD_HANDLERS": handlers})
        dh = DownloadHandlers(crawler)
        assert "scheme" in dh._schemes
        assert "scheme" not in dh._handlers
        assert "scheme" in dh._notconfigured

    def test_disabled_handler(self):
        handlers = {"scheme": None}
        crawler = get_crawler(settings_dict={"DOWNLOAD_HANDLERS": handlers})
        dh = DownloadHandlers(crawler)
        assert "scheme" not in dh._schemes
        for scheme in handlers:  # force load handlers
            dh._get_handler(scheme)
        assert "scheme" not in dh._handlers
        assert "scheme" in dh._notconfigured

    def test_lazy_handlers(self):
        handlers = {"scheme": DummyLazyDH}
        crawler = get_crawler(settings_dict={"DOWNLOAD_HANDLERS": handlers})
        dh = DownloadHandlers(crawler)
        assert "scheme" in dh._schemes
        assert "scheme" not in dh._handlers
        for scheme in handlers:  # force load lazy handler
            dh._get_handler(scheme)
        assert "scheme" in dh._handlers
        assert "scheme" not in dh._notconfigured


class TestFile(unittest.TestCase):
    def setUp(self):
        # add a special char to check that they are handled correctly
        self.fd, self.tmpname = mkstemp(suffix="^")
        Path(self.tmpname).write_text("0123456789", encoding="utf-8")
        handler = build_from_crawler(FileDownloadHandler, get_crawler())
        self.download_request = handler.download_request

    def tearDown(self):
        os.close(self.fd)
        Path(self.tmpname).unlink()

    def test_download(self):
        def _test(response):
            assert response.url == request.url
            assert response.status == 200
            assert response.body == b"0123456789"
            assert response.protocol is None

        request = Request(path_to_file_uri(self.tmpname))
        assert request.url.upper().endswith("%5E")
        return self.download_request(request, Spider("foo")).addCallback(_test)

    def test_non_existent(self):
        request = Request(path_to_file_uri(mkdtemp()))
        d = self.download_request(request, Spider("foo"))
        return self.assertFailure(d, OSError)


class ContentLengthHeaderResource(resource.Resource):
    """
    A testing resource which renders itself as the value of the Content-Length
    header from the request.
    """

    def render(self, request):
        return request.requestHeaders.getRawHeaders(b"content-length")[0]


class ChunkedResource(resource.Resource):
    def render(self, request):
        def response():
            request.write(b"chunked ")
            request.write(b"content\n")
            request.finish()

        reactor.callLater(0, response)
        return server.NOT_DONE_YET


class BrokenChunkedResource(resource.Resource):
    def render(self, request):
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


class TestHttp(unittest.TestCase, ABC):
    scheme = "http"

    # only used for HTTPS tests
    keyfile = "keys/localhost.key"
    certfile = "keys/localhost.crt"

    @property
    @abstractmethod
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        raise NotImplementedError

    def setUp(self):
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
        self.download_request = self.download_handler.download_request

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.port.stopListening()
        if hasattr(self.download_handler, "close"):
            yield self.download_handler.close()
        shutil.rmtree(self.tmpname)

    def getURL(self, path):
        return f"{self.scheme}://{self.host}:{self.portno}/{path}"

    def test_download(self):
        request = Request(self.getURL("file"))
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEqual, b"0123456789")
        return d

    def test_download_head(self):
        request = Request(self.getURL("file"), method="HEAD")
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEqual, b"")
        return d

    def test_redirect_status(self):
        request = Request(self.getURL("redirect"))
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.status)
        d.addCallback(self.assertEqual, 302)
        return d

    def test_redirect_status_head(self):
        request = Request(self.getURL("redirect"), method="HEAD")
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.status)
        d.addCallback(self.assertEqual, 302)
        return d

    @defer.inlineCallbacks
    def test_timeout_download_from_spider_nodata_rcvd(self):
        if self.reactor_pytest != "default" and sys.platform == "win32":
            # https://twistedmatrix.com/trac/ticket/10279
            raise unittest.SkipTest(
                "This test produces DirtyReactorAggregateError on Windows with asyncio"
            )

        # client connects but no data is received
        spider = Spider("foo")
        meta = {"download_timeout": 0.5}
        request = Request(self.getURL("wait"), meta=meta)
        d = self.download_request(request, spider)
        yield self.assertFailure(d, defer.TimeoutError, error.TimeoutError)

    @defer.inlineCallbacks
    def test_timeout_download_from_spider_server_hangs(self):
        if self.reactor_pytest != "default" and sys.platform == "win32":
            # https://twistedmatrix.com/trac/ticket/10279
            raise unittest.SkipTest(
                "This test produces DirtyReactorAggregateError on Windows with asyncio"
            )
        # client connects, server send headers and some body bytes but hangs
        spider = Spider("foo")
        meta = {"download_timeout": 0.5}
        request = Request(self.getURL("hang-after-headers"), meta=meta)
        d = self.download_request(request, spider)
        yield self.assertFailure(d, defer.TimeoutError, error.TimeoutError)

    def test_host_header_not_in_request_headers(self):
        def _test(response):
            assert response.body == to_bytes(f"{self.host}:{self.portno}")
            assert not request.headers

        request = Request(self.getURL("host"))
        return self.download_request(request, Spider("foo")).addCallback(_test)

    def test_host_header_seted_in_request_headers(self):
        host = self.host + ":" + str(self.portno)

        def _test(response):
            assert response.body == host.encode()
            assert request.headers.get("Host") == host.encode()

        request = Request(self.getURL("host"), headers={"Host": host})
        return self.download_request(request, Spider("foo")).addCallback(_test)

    def test_content_length_zero_bodyless_post_request_headers(self):
        """Tests if "Content-Length: 0" is sent for bodyless POST requests.

        This is not strictly required by HTTP RFCs but can cause trouble
        for some web servers.
        See:
        https://github.com/scrapy/scrapy/issues/823
        https://issues.apache.org/jira/browse/TS-2902
        https://github.com/kennethreitz/requests/issues/405
        https://bugs.python.org/issue14721
        """

        def _test(response):
            assert response.body == b"0"

        request = Request(self.getURL("contentlength"), method="POST")
        return self.download_request(request, Spider("foo")).addCallback(_test)

    def test_content_length_zero_bodyless_post_only_one(self):
        def _test(response):
            import json

            headers = Headers(json.loads(response.text)["headers"])
            contentlengths = headers.getlist("Content-Length")
            assert len(contentlengths) == 1
            assert contentlengths == [b"0"]

        request = Request(self.getURL("echo"), method="POST")
        return self.download_request(request, Spider("foo")).addCallback(_test)

    def test_payload(self):
        body = b"1" * 100  # PayloadResource requires body length to be 100
        request = Request(self.getURL("payload"), method="POST", body=body)
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEqual, body)
        return d

    def test_response_header_content_length(self):
        request = Request(self.getURL("file"), method=b"GET")
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.headers[b"content-length"])
        d.addCallback(self.assertEqual, b"159")
        return d

    def _test_response_class(self, filename, body, response_class):
        def _test(response):
            assert type(response) is response_class  # pylint: disable=unidiomatic-typecheck

        request = Request(self.getURL(filename), body=body)
        return self.download_request(request, Spider("foo")).addCallback(_test)

    def test_response_class_from_url(self):
        return self._test_response_class("foo.html", b"", HtmlResponse)

    def test_response_class_from_body(self):
        return self._test_response_class(
            "foo",
            b"<!DOCTYPE html>\n<title>.</title>",
            HtmlResponse,
        )

    def test_get_duplicate_header(self):
        def _test(response):
            assert response.headers.getlist(b"Set-Cookie") == [b"a=b", b"c=d"]

        request = Request(self.getURL("duplicate-header"))
        return self.download_request(request, Spider("foo")).addCallback(_test)


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestHttp10(TestHttp):
    """HTTP 1.0 test case"""

    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return HTTP10DownloadHandler

    def test_protocol(self):
        request = Request(self.getURL("host"), method="GET")
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.protocol)
        d.addCallback(self.assertEqual, "HTTP/1.0")
        return d


class TestHttps10(TestHttp10):
    scheme = "https"


class TestHttp11(TestHttp):
    """HTTP 1.1 test case"""

    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return HTTP11DownloadHandler

    def test_download_without_maxsize_limit(self):
        request = Request(self.getURL("file"))
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEqual, b"0123456789")
        return d

    def test_response_class_choosing_request(self):
        """Tests choosing of correct response type
        in case of Content-Type is empty but body contains text.
        """
        body = b"Some plain text\ndata with tabs\t and null bytes\0"

        def _test_type(response):
            assert type(response) is TextResponse  # pylint: disable=unidiomatic-typecheck

        request = Request(self.getURL("nocontenttype"), body=body)
        d = self.download_request(request, Spider("foo"))
        d.addCallback(_test_type)
        return d

    @defer.inlineCallbacks
    def test_download_with_maxsize(self):
        request = Request(self.getURL("file"))

        # 10 is minimal size for this request and the limit is only counted on
        # response body. (regardless of headers)
        d = self.download_request(request, Spider("foo", download_maxsize=10))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEqual, b"0123456789")
        yield d

        d = self.download_request(request, Spider("foo", download_maxsize=9))
        yield self.assertFailure(d, defer.CancelledError, error.ConnectionAborted)

    @defer.inlineCallbacks
    def test_download_with_maxsize_very_large_file(self):
        with mock.patch("scrapy.core.downloader.handlers.http11.logger") as logger:
            request = Request(self.getURL("largechunkedfile"))

            def check(logger):
                logger.warning.assert_called_once_with(mock.ANY, mock.ANY)

            d = self.download_request(request, Spider("foo", download_maxsize=1500))
            yield self.assertFailure(d, defer.CancelledError, error.ConnectionAborted)

            # As the error message is logged in the dataReceived callback, we
            # have to give a bit of time to the reactor to process the queue
            # after closing the connection.
            d = defer.Deferred()
            d.addCallback(check)
            reactor.callLater(0.1, d.callback, logger)
            yield d

    @defer.inlineCallbacks
    def test_download_with_maxsize_per_req(self):
        meta = {"download_maxsize": 2}
        request = Request(self.getURL("file"), meta=meta)
        d = self.download_request(request, Spider("foo"))
        yield self.assertFailure(d, defer.CancelledError, error.ConnectionAborted)

    @defer.inlineCallbacks
    def test_download_with_small_maxsize_per_spider(self):
        request = Request(self.getURL("file"))
        d = self.download_request(request, Spider("foo", download_maxsize=2))
        yield self.assertFailure(d, defer.CancelledError, error.ConnectionAborted)

    def test_download_with_large_maxsize_per_spider(self):
        request = Request(self.getURL("file"))
        d = self.download_request(request, Spider("foo", download_maxsize=100))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEqual, b"0123456789")
        return d

    def test_download_chunked_content(self):
        request = Request(self.getURL("chunked"))
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEqual, b"chunked content\n")
        return d

    def test_download_broken_content_cause_data_loss(self, url="broken"):
        request = Request(self.getURL(url))
        d = self.download_request(request, Spider("foo"))

        def checkDataLoss(failure):
            if failure.check(ResponseFailed) and any(
                r.check(_DataLoss) for r in failure.value.reasons
            ):
                return None
            return failure

        d.addCallback(lambda _: self.fail("No DataLoss exception"))
        d.addErrback(checkDataLoss)
        return d

    def test_download_broken_chunked_content_cause_data_loss(self):
        return self.test_download_broken_content_cause_data_loss("broken-chunked")

    def test_download_broken_content_allow_data_loss(self, url="broken"):
        request = Request(self.getURL(url), meta={"download_fail_on_dataloss": False})
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.flags)
        d.addCallback(self.assertEqual, ["dataloss"])
        return d

    def test_download_broken_chunked_content_allow_data_loss(self):
        return self.test_download_broken_content_allow_data_loss("broken-chunked")

    def test_download_broken_content_allow_data_loss_via_setting(self, url="broken"):
        crawler = get_crawler(settings_dict={"DOWNLOAD_FAIL_ON_DATALOSS": False})
        download_handler = build_from_crawler(self.download_handler_cls, crawler)
        request = Request(self.getURL(url))
        d = download_handler.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.flags)
        d.addCallback(self.assertEqual, ["dataloss"])
        return d

    def test_download_broken_chunked_content_allow_data_loss_via_setting(self):
        return self.test_download_broken_content_allow_data_loss_via_setting(
            "broken-chunked"
        )

    def test_protocol(self):
        request = Request(self.getURL("host"), method="GET")
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.protocol)
        d.addCallback(self.assertEqual, "HTTP/1.1")
        return d


class TestHttps11(TestHttp11):
    scheme = "https"

    tls_log_message = (
        'SSL connection certificate: issuer "/C=IE/O=Scrapy/CN=localhost", '
        'subject "/C=IE/O=Scrapy/CN=localhost"'
    )

    @defer.inlineCallbacks
    def test_tls_logging(self):
        crawler = get_crawler(
            settings_dict={"DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING": True}
        )
        download_handler = build_from_crawler(self.download_handler_cls, crawler)
        try:
            with LogCapture() as log_capture:
                request = Request(self.getURL("file"))
                d = download_handler.download_request(request, Spider("foo"))
                d.addCallback(lambda r: r.body)
                d.addCallback(self.assertEqual, b"0123456789")
                yield d
                log_capture.check_present(
                    ("scrapy.core.downloader.tls", "DEBUG", self.tls_log_message)
                )
        finally:
            yield download_handler.close()


class TestSimpleHttps(unittest.TestCase):
    """Base class for special cases tested with just one simple request"""

    keyfile = "keys/localhost.key"
    certfile = "keys/localhost.crt"
    cipher_string: str | None = None

    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return HTTP11DownloadHandler

    def setUp(self):
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
        self.download_request = self.download_handler.download_request

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.port.stopListening()
        if hasattr(self.download_handler, "close"):
            yield self.download_handler.close()
        shutil.rmtree(self.tmpname)

    def getURL(self, path):
        return f"https://{self.host}:{self.portno}/{path}"

    def test_download(self):
        request = Request(self.getURL("file"))
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEqual, b"0123456789")
        return d


class TestHttps11WrongHostname(TestSimpleHttps):
    # above tests use a server certificate for "localhost",
    # client connection to "localhost" too.
    # here we test that even if the server certificate is for another domain,
    # "www.example.com" in this case,
    # the tests still pass
    keyfile = "keys/example-com.key.pem"
    certfile = "keys/example-com.cert.pem"


class TestHttps11InvalidDNSId(TestSimpleHttps):
    """Connect to HTTPS hosts with IP while certificate uses domain names IDs."""

    def setUp(self):
        super().setUp()
        self.host = "127.0.0.1"


class TestHttps11InvalidDNSPattern(TestSimpleHttps):
    """Connect to HTTPS hosts where the certificate are issued to an ip instead of a domain."""

    keyfile = "keys/localhost.ip.key"
    certfile = "keys/localhost.ip.crt"


class TestHttps11CustomCiphers(TestSimpleHttps):
    cipher_string = "CAMELLIA256-SHA"


class TestHttp11MockServer(unittest.TestCase):
    """HTTP 1.1 test case with MockServer"""

    settings_dict: dict | None = None
    is_secure = False

    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_download_with_content_length(self):
        crawler = get_crawler(SingleRequestSpider, self.settings_dict)
        # http://localhost:8998/partial set Content-Length to 1024, use download_maxsize= 1000 to avoid
        # download it
        yield crawler.crawl(
            seed=Request(
                url=self.mockserver.url("/partial", is_secure=self.is_secure),
                meta={"download_maxsize": 1000},
            )
        )
        failure = crawler.spider.meta["failure"]
        assert isinstance(failure.value, defer.CancelledError)

    @defer.inlineCallbacks
    def test_download(self):
        crawler = get_crawler(SingleRequestSpider, self.settings_dict)
        yield crawler.crawl(
            seed=Request(url=self.mockserver.url("", is_secure=self.is_secure))
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


class TestHttpProxy(unittest.TestCase, ABC):
    expected_http_proxy_request_body = b"http://example.com"

    @property
    @abstractmethod
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        raise NotImplementedError

    def setUp(self):
        site = server.Site(UriResource(), timeout=None)
        wrapper = WrappingFactory(site)
        self.port = reactor.listenTCP(0, wrapper, interface="127.0.0.1")
        self.portno = self.port.getHost().port
        self.download_handler = build_from_crawler(
            self.download_handler_cls, get_crawler()
        )
        self.download_request = self.download_handler.download_request

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.port.stopListening()
        if hasattr(self.download_handler, "close"):
            yield self.download_handler.close()

    def getURL(self, path):
        return f"http://127.0.0.1:{self.portno}/{path}"

    def test_download_with_proxy(self):
        def _test(response):
            assert response.status == 200
            assert response.url == request.url
            assert response.body == self.expected_http_proxy_request_body

        http_proxy = self.getURL("")
        request = Request("http://example.com", meta={"proxy": http_proxy})
        return self.download_request(request, Spider("foo")).addCallback(_test)

    def test_download_without_proxy(self):
        def _test(response):
            assert response.status == 200
            assert response.url == request.url
            assert response.body == b"/path/to/resource"

        request = Request(self.getURL("path/to/resource"))
        return self.download_request(request, Spider("foo")).addCallback(_test)


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestHttp10Proxy(TestHttpProxy):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return HTTP10DownloadHandler


class TestHttp11Proxy(TestHttpProxy):
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return HTTP11DownloadHandler

    @defer.inlineCallbacks
    def test_download_with_proxy_https_timeout(self):
        """Test TunnelingTCP4ClientEndpoint"""
        if NON_EXISTING_RESOLVABLE:
            raise SkipTest("Non-existing hosts are resolvable")
        http_proxy = self.getURL("")
        domain = "https://no-such-domain.nosuch"
        request = Request(domain, meta={"proxy": http_proxy, "download_timeout": 0.2})
        d = self.download_request(request, Spider("foo"))
        timeout = yield self.assertFailure(d, error.TimeoutError)
        assert domain in timeout.osError

    def test_download_with_proxy_without_http_scheme(self):
        def _test(response):
            assert response.status == 200
            assert response.url == request.url
            assert response.body == self.expected_http_proxy_request_body

        http_proxy = self.getURL("").replace("http://", "")
        request = Request("http://example.com", meta={"proxy": http_proxy})
        return self.download_request(request, Spider("foo")).addCallback(_test)


class HttpDownloadHandlerMock:
    def __init__(self, *args, **kwargs):
        pass

    def download_request(self, request, spider):
        return request


@pytest.mark.requires_botocore
class TestS3Anon:
    def setup_method(self):
        crawler = get_crawler()
        self.s3reqh = build_from_crawler(
            S3DownloadHandler,
            crawler,
            httpdownloadhandler=HttpDownloadHandlerMock,
            # anon=True, # implicit
        )
        self.download_request = self.s3reqh.download_request
        self.spider = Spider("foo")

    def test_anon_request(self):
        req = Request("s3://aws-publicdatasets/")
        httpreq = self.download_request(req, self.spider)
        assert hasattr(self.s3reqh, "anon")
        assert self.s3reqh.anon
        assert httpreq.url == "http://aws-publicdatasets.s3.amazonaws.com/"


@pytest.mark.requires_botocore
class TestS3:
    download_handler_cls: type = S3DownloadHandler

    # test use same example keys than amazon developer guide
    # http://s3.amazonaws.com/awsdocs/S3/20060301/s3-dg-20060301.pdf
    # and the tests described here are the examples from that manual

    AWS_ACCESS_KEY_ID = "0PN5J17HBGZHT7JJ3X82"
    AWS_SECRET_ACCESS_KEY = "uV3F3YluFJax1cknvbcGwgjvx4QpvB+leU8dUj2o"

    def setup_method(self):
        crawler = get_crawler()
        s3reqh = build_from_crawler(
            S3DownloadHandler,
            crawler,
            aws_access_key_id=self.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.AWS_SECRET_ACCESS_KEY,
            httpdownloadhandler=HttpDownloadHandlerMock,
        )
        self.download_request = s3reqh.download_request
        self.spider = Spider("foo")

    @contextlib.contextmanager
    def _mocked_date(self, date):
        try:
            import botocore.auth  # noqa: F401
        except ImportError:
            yield
        else:
            # We need to mock botocore.auth.formatdate, because otherwise
            # botocore overrides Date header with current date and time
            # and Authorization header is different each time
            with mock.patch("botocore.auth.formatdate") as mock_formatdate:
                mock_formatdate.return_value = date
                yield

    def test_extra_kw(self):
        crawler = get_crawler()
        with pytest.raises((TypeError, NotConfigured)):
            build_from_crawler(
                S3DownloadHandler,
                crawler,
                extra_kw=True,
            )

    def test_request_signing1(self):
        # gets an object from the johnsmith bucket.
        date = "Tue, 27 Mar 2007 19:36:42 +0000"
        req = Request("s3://johnsmith/photos/puppy.jpg", headers={"Date": date})
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        assert (
            httpreq.headers["Authorization"]
            == b"AWS 0PN5J17HBGZHT7JJ3X82:xXjDGYUmKxnwqr5KXNPGldn5LbA="
        )

    def test_request_signing2(self):
        # puts an object into the johnsmith bucket.
        date = "Tue, 27 Mar 2007 21:15:45 +0000"
        req = Request(
            "s3://johnsmith/photos/puppy.jpg",
            method="PUT",
            headers={
                "Content-Type": "image/jpeg",
                "Date": date,
                "Content-Length": "94328",
            },
        )
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        assert (
            httpreq.headers["Authorization"]
            == b"AWS 0PN5J17HBGZHT7JJ3X82:hcicpDDvL9SsO6AkvxqmIWkmOuQ="
        )

    def test_request_signing3(self):
        # lists the content of the johnsmith bucket.
        date = "Tue, 27 Mar 2007 19:42:41 +0000"
        req = Request(
            "s3://johnsmith/?prefix=photos&max-keys=50&marker=puppy",
            method="GET",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Date": date,
            },
        )
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        assert (
            httpreq.headers["Authorization"]
            == b"AWS 0PN5J17HBGZHT7JJ3X82:jsRt/rhG+Vtp88HrYL706QhE4w4="
        )

    def test_request_signing4(self):
        # fetches the access control policy sub-resource for the 'johnsmith' bucket.
        date = "Tue, 27 Mar 2007 19:44:46 +0000"
        req = Request("s3://johnsmith/?acl", method="GET", headers={"Date": date})
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        assert (
            httpreq.headers["Authorization"]
            == b"AWS 0PN5J17HBGZHT7JJ3X82:thdUi9VAkzhkniLj96JIrOPGi0g="
        )

    def test_request_signing6(self):
        # uploads an object to a CNAME style virtual hosted bucket with metadata.
        date = "Tue, 27 Mar 2007 21:06:08 +0000"
        req = Request(
            "s3://static.johnsmith.net:8080/db-backup.dat.gz",
            method="PUT",
            headers={
                "User-Agent": "curl/7.15.5",
                "Host": "static.johnsmith.net:8080",
                "Date": date,
                "x-amz-acl": "public-read",
                "content-type": "application/x-download",
                "Content-MD5": "4gJE4saaMU4BqNR0kLY+lw==",
                "X-Amz-Meta-ReviewedBy": "joe@johnsmith.net,jane@johnsmith.net",
                "X-Amz-Meta-FileChecksum": "0x02661779",
                "X-Amz-Meta-ChecksumAlgorithm": "crc32",
                "Content-Disposition": "attachment; filename=database.dat",
                "Content-Encoding": "gzip",
                "Content-Length": "5913339",
            },
        )
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        assert (
            httpreq.headers["Authorization"]
            == b"AWS 0PN5J17HBGZHT7JJ3X82:C0FlOtU8Ylb9KDTpZqYkZPX91iI="
        )

    def test_request_signing7(self):
        # ensure that spaces are quoted properly before signing
        date = "Tue, 27 Mar 2007 19:42:41 +0000"
        req = Request(
            "s3://johnsmith/photos/my puppy.jpg?response-content-disposition=my puppy.jpg",
            method="GET",
            headers={"Date": date},
        )
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        assert (
            httpreq.headers["Authorization"]
            == b"AWS 0PN5J17HBGZHT7JJ3X82:+CfvG8EZ3YccOrRVMXNaK2eKZmM="
        )


class TestFTPBase(unittest.TestCase):
    username = "scrapy"
    password = "passwd"
    req_meta = {"ftp_user": username, "ftp_password": password}

    test_files = (
        ("file.txt", b"I have the power!"),
        ("file with spaces.txt", b"Moooooooooo power!"),
        ("html-file-without-extension", b"<!DOCTYPE html>\n<title>.</title>"),
    )

    def setUp(self):
        # setup dirs and test file
        self.directory = Path(mkdtemp())
        userdir = self.directory / self.username
        userdir.mkdir()
        for filename, content in self.test_files:
            (userdir / filename).write_bytes(content)

        # setup server
        realm = FTPRealm(
            anonymousRoot=str(self.directory), userHome=str(self.directory)
        )
        p = portal.Portal(realm)
        users_checker = checkers.InMemoryUsernamePasswordDatabaseDontUse()
        users_checker.addUser(self.username, self.password)
        p.registerChecker(users_checker, credentials.IUsernamePassword)
        self.factory = FTPFactory(portal=p)
        self.port = reactor.listenTCP(0, self.factory, interface="127.0.0.1")
        self.portNum = self.port.getHost().port
        crawler = get_crawler()
        self.download_handler = build_from_crawler(FTPDownloadHandler, crawler)
        self.addCleanup(self.port.stopListening)

    def tearDown(self):
        shutil.rmtree(self.directory)

    def _add_test_callbacks(self, deferred, callback=None, errback=None):
        def _clean(data):
            self.download_handler.client.transport.loseConnection()
            return data

        deferred.addCallback(_clean)
        if callback:
            deferred.addCallback(callback)
        if errback:
            deferred.addErrback(errback)
        return deferred

    def test_ftp_download_success(self):
        request = Request(
            url=f"ftp://127.0.0.1:{self.portNum}/file.txt", meta=self.req_meta
        )
        d = self.download_handler.download_request(request, None)

        def _test(r):
            assert r.status == 200
            assert r.body == b"I have the power!"
            assert r.headers == {b"Local Filename": [b""], b"Size": [b"17"]}
            assert r.protocol is None

        return self._add_test_callbacks(d, _test)

    def test_ftp_download_path_with_spaces(self):
        request = Request(
            url=f"ftp://127.0.0.1:{self.portNum}/file with spaces.txt",
            meta=self.req_meta,
        )
        d = self.download_handler.download_request(request, None)

        def _test(r):
            assert r.status == 200
            assert r.body == b"Moooooooooo power!"
            assert r.headers == {b"Local Filename": [b""], b"Size": [b"18"]}

        return self._add_test_callbacks(d, _test)

    def test_ftp_download_nonexistent(self):
        request = Request(
            url=f"ftp://127.0.0.1:{self.portNum}/nonexistent.txt", meta=self.req_meta
        )
        d = self.download_handler.download_request(request, None)

        def _test(r):
            assert r.status == 404

        return self._add_test_callbacks(d, _test)

    def test_ftp_local_filename(self):
        f, local_fname = mkstemp()
        fname_bytes = to_bytes(local_fname)
        local_fname = Path(local_fname)
        os.close(f)
        meta = {"ftp_local_filename": fname_bytes}
        meta.update(self.req_meta)
        request = Request(url=f"ftp://127.0.0.1:{self.portNum}/file.txt", meta=meta)
        d = self.download_handler.download_request(request, None)

        def _test(r):
            assert r.body == fname_bytes
            assert r.headers == {b"Local Filename": [fname_bytes], b"Size": [b"17"]}
            assert local_fname.exists()
            assert local_fname.read_bytes() == b"I have the power!"
            local_fname.unlink()

        return self._add_test_callbacks(d, _test)

    def _test_response_class(self, filename, response_class):
        f, local_fname = mkstemp()
        local_fname = Path(local_fname)
        os.close(f)
        meta = {}
        meta.update(self.req_meta)
        request = Request(url=f"ftp://127.0.0.1:{self.portNum}/{filename}", meta=meta)
        d = self.download_handler.download_request(request, None)

        def _test(r):
            assert type(r) is response_class  # pylint: disable=unidiomatic-typecheck
            local_fname.unlink()

        return self._add_test_callbacks(d, _test)

    def test_response_class_from_url(self):
        return self._test_response_class("file.txt", TextResponse)

    def test_response_class_from_body(self):
        return self._test_response_class("html-file-without-extension", HtmlResponse)


class TestFTP(TestFTPBase):
    def test_invalid_credentials(self):
        if self.reactor_pytest != "default" and sys.platform == "win32":
            raise unittest.SkipTest(
                "This test produces DirtyReactorAggregateError on Windows with asyncio"
            )
        from twisted.protocols.ftp import ConnectionLost

        meta = dict(self.req_meta)
        meta.update({"ftp_password": "invalid"})
        request = Request(url=f"ftp://127.0.0.1:{self.portNum}/file.txt", meta=meta)
        d = self.download_handler.download_request(request, None)

        def _test(r):
            assert r.type == ConnectionLost

        return self._add_test_callbacks(d, errback=_test)


class TestAnonymousFTP(TestFTPBase):
    username = "anonymous"
    req_meta = {}

    def setUp(self):
        # setup dir and test file
        self.directory = Path(mkdtemp())
        for filename, content in self.test_files:
            (self.directory / filename).write_bytes(content)

        # setup server for anonymous access
        realm = FTPRealm(anonymousRoot=str(self.directory))
        p = portal.Portal(realm)
        p.registerChecker(checkers.AllowAnonymousAccess(), credentials.IAnonymous)

        self.factory = FTPFactory(portal=p, userAnonymous=self.username)
        self.port = reactor.listenTCP(0, self.factory, interface="127.0.0.1")
        self.portNum = self.port.getHost().port
        crawler = get_crawler()
        self.download_handler = build_from_crawler(FTPDownloadHandler, crawler)
        self.addCleanup(self.port.stopListening)

    def tearDown(self):
        shutil.rmtree(self.directory)


class TestDataURI(unittest.TestCase):
    def setUp(self):
        crawler = get_crawler()
        self.download_handler = build_from_crawler(DataURIDownloadHandler, crawler)
        self.download_request = self.download_handler.download_request
        self.spider = Spider("foo")

    def test_response_attrs(self):
        uri = "data:,A%20brief%20note"

        def _test(response):
            assert response.url == uri
            assert not response.headers

        request = Request(uri)
        return self.download_request(request, self.spider).addCallback(_test)

    def test_default_mediatype_encoding(self):
        def _test(response):
            assert response.text == "A brief note"
            assert type(response) is responsetypes.from_mimetype("text/plain")  # pylint: disable=unidiomatic-typecheck
            assert response.encoding == "US-ASCII"

        request = Request("data:,A%20brief%20note")
        return self.download_request(request, self.spider).addCallback(_test)

    def test_default_mediatype(self):
        def _test(response):
            assert response.text == "\u038e\u03a3\u038e"
            assert type(response) is responsetypes.from_mimetype("text/plain")  # pylint: disable=unidiomatic-typecheck
            assert response.encoding == "iso-8859-7"

        request = Request("data:;charset=iso-8859-7,%be%d3%be")
        return self.download_request(request, self.spider).addCallback(_test)

    def test_text_charset(self):
        def _test(response):
            assert response.text == "\u038e\u03a3\u038e"
            assert response.body == b"\xbe\xd3\xbe"
            assert response.encoding == "iso-8859-7"

        request = Request("data:text/plain;charset=iso-8859-7,%be%d3%be")
        return self.download_request(request, self.spider).addCallback(_test)

    def test_mediatype_parameters(self):
        def _test(response):
            assert response.text == "\u038e\u03a3\u038e"
            assert type(response) is responsetypes.from_mimetype("text/plain")  # pylint: disable=unidiomatic-typecheck
            assert response.encoding == "utf-8"

        request = Request(
            "data:text/plain;foo=%22foo;bar%5C%22%22;"
            "charset=utf-8;bar=%22foo;%5C%22 foo ;/,%22"
            ",%CE%8E%CE%A3%CE%8E"
        )
        return self.download_request(request, self.spider).addCallback(_test)

    def test_base64(self):
        def _test(response):
            assert response.text == "Hello, world."

        request = Request("data:text/plain;base64,SGVsbG8sIHdvcmxkLg%3D%3D")
        return self.download_request(request, self.spider).addCallback(_test)

    def test_protocol(self):
        def _test(response):
            assert response.protocol is None

        request = Request("data:,")
        return self.download_request(request, self.spider).addCallback(_test)
