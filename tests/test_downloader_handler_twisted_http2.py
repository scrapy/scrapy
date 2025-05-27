"""Tests for scrapy.core.downloader.handlers.http2.H2DownloadHandler."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from testfixtures import LogCapture
from twisted.internet import defer, error, reactor
from twisted.web import server
from twisted.web.error import SchemeNotSupported
from twisted.web.http import H2_ENABLED

from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
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
)

if TYPE_CHECKING:
    from scrapy.core.downloader.handlers import DownloadHandlerProtocol


pytestmark = pytest.mark.skipif(
    not H2_ENABLED, reason="HTTP/2 support in Twisted is not enabled"
)


class H2DownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        # the import can fail when H2_ENABLED is False
        from scrapy.core.downloader.handlers.http2 import H2DownloadHandler

        return H2DownloadHandler


class TestHttps2(H2DownloadHandlerMixin, TestHttps11Base):
    HTTP2_DATALOSS_SKIP_REASON = "Content-Length mismatch raises InvalidBodyLengthError"

    def test_protocol(self):
        request = Request(self.getURL("host"), method="GET")
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.protocol)
        d.addCallback(self.assertEqual, "h2")
        return d

    @defer.inlineCallbacks
    def test_download_with_maxsize_very_large_file(self):
        with mock.patch("scrapy.core.http2.stream.logger") as logger:
            request = Request(self.getURL("largechunkedfile"))

            def check(logger):
                logger.error.assert_called_once_with(mock.ANY)

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
    def test_unsupported_scheme(self):
        request = Request("ftp://unsupported.scheme")
        d = self.download_request(request, Spider("foo"))
        yield self.assertFailure(d, SchemeNotSupported)

    def test_download_broken_content_cause_data_loss(self, url="broken"):
        pytest.skip(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_cause_data_loss(self):
        pytest.skip(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_content_allow_data_loss(self, url="broken"):
        pytest.skip(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_allow_data_loss(self):
        pytest.skip(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_content_allow_data_loss_via_setting(self, url="broken"):
        pytest.skip(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_allow_data_loss_via_setting(self):
        pytest.skip(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_concurrent_requests_same_domain(self):
        spider = Spider("foo")

        request1 = Request(self.getURL("file"))
        d1 = self.download_request(request1, spider)
        d1.addCallback(lambda r: r.body)
        d1.addCallback(self.assertEqual, b"0123456789")

        request2 = Request(self.getURL("echo"), method="POST")
        d2 = self.download_request(request2, spider)
        d2.addCallback(lambda r: r.headers["Content-Length"])
        d2.addCallback(self.assertEqual, b"79")

        return defer.DeferredList([d1, d2])

    @pytest.mark.xfail(reason="https://github.com/python-hyper/h2/issues/1247")
    def test_connect_request(self):
        request = Request(self.getURL("file"), method="CONNECT")
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEqual, b"")
        return d

    def test_custom_content_length_good(self):
        request = Request(self.getURL("contentlength"))
        custom_content_length = str(len(request.body))
        request.headers["Content-Length"] = custom_content_length
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.text)
        d.addCallback(self.assertEqual, custom_content_length)
        return d

    def test_custom_content_length_bad(self):
        request = Request(self.getURL("contentlength"))
        actual_content_length = str(len(request.body))
        bad_content_length = str(len(request.body) + 1)
        request.headers["Content-Length"] = bad_content_length
        log = LogCapture()
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.text)
        d.addCallback(self.assertEqual, actual_content_length)
        d.addCallback(
            lambda _: log.check_present(
                (
                    "scrapy.core.http2.stream",
                    "WARNING",
                    f"Ignoring bad Content-Length header "
                    f"{bad_content_length!r} of request {request}, sending "
                    f"{actual_content_length!r} instead",
                )
            )
        )
        d.addCallback(lambda _: log.uninstall())
        return d

    def test_duplicate_header(self):
        request = Request(self.getURL("echo"))
        header, value1, value2 = "Custom-Header", "foo", "bar"
        request.headers.appendlist(header, value1)
        request.headers.appendlist(header, value2)
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: json.loads(r.text)["headers"][header])
        d.addCallback(self.assertEqual, [value1, value2])
        return d


class Https2WrongHostnameTestCase(H2DownloadHandlerMixin, TestHttpsWrongHostnameBase):
    pass


class Https2InvalidDNSId(H2DownloadHandlerMixin, TestHttpsInvalidDNSIdBase):
    pass


class Https2InvalidDNSPattern(H2DownloadHandlerMixin, TestHttpsInvalidDNSPatternBase):
    pass


class Https2CustomCiphers(H2DownloadHandlerMixin, TestHttpsCustomCiphersBase):
    pass


class Http2MockServerTestCase(TestHttpMockServerBase):
    """HTTP 2.0 test case with MockServer"""

    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return {
            "DOWNLOAD_HANDLERS": {
                "https": "scrapy.core.downloader.handlers.http2.H2DownloadHandler"
            }
        }

    is_secure = True


class Https2ProxyTestCase(H2DownloadHandlerMixin, TestHttpProxyBase):
    # only used for HTTPS tests
    keyfile = "keys/localhost.key"
    certfile = "keys/localhost.crt"

    scheme = "https"
    host = "127.0.0.1"

    expected_http_proxy_request_body = b"/"

    def setUp(self):
        site = server.Site(UriResource(), timeout=None)
        self.port = reactor.listenSSL(
            0,
            site,
            ssl_context_factory(self.keyfile, self.certfile),
            interface=self.host,
        )
        self.portno = self.port.getHost().port
        self.download_handler = build_from_crawler(
            self.download_handler_cls, get_crawler()
        )
        self.download_request = self.download_handler.download_request

    def getURL(self, path):
        return f"{self.scheme}://{self.host}:{self.portno}/{path}"

    @defer.inlineCallbacks
    def test_download_with_proxy_https_timeout(self):
        with pytest.raises(NotImplementedError):
            yield super().test_download_with_proxy_https_timeout()
