"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import Mock

import pytest
from twisted.internet.testing import StringTransport
from twisted.web._newclient import Request as TxClientRequest
from twisted.web._newclient import RequestNotSent
from twisted.web.http_headers import Headers as TxHeaders

from scrapy import Spider
from scrapy.core.downloader.handlers.http11 import (
    HTTP11DownloadHandler,
    _ScrapyHTTP11ClientProtocol,
    _TunnelingTCP4ClientEndpoint,
)
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured, ResponseHeadersTooLargeError
from tests.utils.bases.download_handlers_http import (
    TestHttpBase,
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

if TYPE_CHECKING:
    from twisted.python.failure import Failure

    from scrapy.core.downloader.handlers import DownloadHandlerProtocol


pytestmark = pytest.mark.requires_reactor  # HTTP11DownloadHandler requires a reactor


class HTTP11DownloadHandlerMixin:
    @property
    def download_handler_cls(self) -> type[DownloadHandlerProtocol]:
        return HTTP11DownloadHandler

    @property
    def settings_dict(self) -> dict[str, Any] | None:
        return {
            "DOWNLOAD_HANDLERS": {
                "http": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
                "https": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
            }
        }


def test_not_configured_without_reactor() -> None:
    crawler = Crawler(Spider, {"TWISTED_REACTOR_ENABLED": False})
    with pytest.raises(NotConfigured):
        HTTP11DownloadHandler.from_crawler(crawler)


class TestHttp(HTTP11DownloadHandlerMixin, TestHttpBase):
    pass


class TestHttps(HTTP11DownloadHandlerMixin, TestHttpsBase):
    pass


class TestSimpleHttps(HTTP11DownloadHandlerMixin, TestSimpleHttpsBase):
    pass


class TestHttpsWrongHostname(HTTP11DownloadHandlerMixin, TestHttpsWrongHostnameBase):
    pass


class TestHttpsInvalidDNSId(HTTP11DownloadHandlerMixin, TestHttpsInvalidDNSIdBase):
    pass


class TestHttpsInvalidDNSPattern(
    HTTP11DownloadHandlerMixin, TestHttpsInvalidDNSPatternBase
):
    pass


class TestHttpsCustomCiphers(HTTP11DownloadHandlerMixin, TestHttpsCustomCiphersBase):
    pass


class TestHttpsTLSVersion(HTTP11DownloadHandlerMixin, TestHttpsTLSVersionBase):
    pass


class TestHttpWithCrawler(HTTP11DownloadHandlerMixin, TestHttpWithCrawlerBase):
    pass


class TestHttpsWithCrawler(TestHttpWithCrawler):
    is_secure = True


class TestHttpProxy(HTTP11DownloadHandlerMixin, TestHttpProxyBase):
    pass


class TestHttpsProxy(HTTP11DownloadHandlerMixin, TestHttpProxyBase):
    is_secure = True
    # not implemented
    handler_supports_tls_in_tls = False


@pytest.mark.requires_mitmproxy
class TestMitmProxy(HTTP11DownloadHandlerMixin, TestMitmProxyBase):
    # not implemented
    handler_supports_tls_in_tls = False


@pytest.mark.requires_internet
class TestRealWebsite(HTTP11DownloadHandlerMixin, TestRealWebsiteBase):
    @property
    def platform_cert_store_works(self) -> bool:
        return sys.platform != "win32"


class TestTunnelingHeadersMaxsize:
    """Tests for the DOWNLOAD_HEADERS_MAXSIZE limit that
    ``_TunnelingTCP4ClientEndpoint`` applies to the response head of the proxy,
    which no HTTP client parses for us."""

    def _get_endpoint(self, headers_maxsize: int) -> _TunnelingTCP4ClientEndpoint:
        from twisted.internet import reactor

        endpoint = _TunnelingTCP4ClientEndpoint(
            reactor=cast("Any", reactor),
            host="example.com",
            port=443,
            proxyConf=("proxy.example.com", 8080, None),
            contextFactory=cast("Any", None),
            headersMaxsize=headers_maxsize,
        )
        endpoint._protocol = cast("Any", Mock())
        endpoint._protocolDataReceived = Mock()
        return endpoint

    def test_over_maxsize(self) -> None:
        endpoint = self._get_endpoint(1024)
        failures: list[Failure] = []
        endpoint._tunnelReadyDeferred.addErrback(failures.append)

        # A proxy response head that never ends.
        for _ in range(3):
            endpoint.processProxyResponse(b"a" * 512)

        assert len(failures) == 1
        assert failures[0].check(ResponseHeadersTooLargeError)
        assert "1024" in str(failures[0].value)
        assert "CONNECT example.com:443" in str(failures[0].value)
        endpoint._protocol.transport.loseConnection.assert_called_once()  # type: ignore[union-attr]

    def test_under_maxsize(self) -> None:
        endpoint = self._get_endpoint(1024)
        failures: list[Failure] = []
        endpoint._tunnelReadyDeferred.addErrback(failures.append)

        endpoint.processProxyResponse(b"a" * 512)

        assert not failures

    def test_maxsize_disabled(self) -> None:
        endpoint = self._get_endpoint(0)
        failures: list[Failure] = []
        endpoint._tunnelReadyDeferred.addErrback(failures.append)

        for _ in range(3):
            endpoint.processProxyResponse(b"a" * 512)

        assert not failures


class TestScrapyHTTP11ClientProtocol:
    """Tests for the response header size limiting that
    ``_ScrapyHTTP11ClientProtocol`` installs on the response parser that
    Twisted builds for each request."""

    @staticmethod
    def _get_protocol() -> _ScrapyHTTP11ClientProtocol:
        protocol = _ScrapyHTTP11ClientProtocol(lambda _: None, 64 * 1024, 32 * 1024)
        protocol.makeConnection(StringTransport())  # type: ignore[no-untyped-call]
        return protocol

    @staticmethod
    def _get_request() -> TxClientRequest:
        return TxClientRequest(
            b"GET", b"/", TxHeaders({b"host": [b"example.com"]}), None
        )

    def test_parser_is_limited(self) -> None:
        protocol = self._get_protocol()
        protocol.request(self._get_request())
        assert protocol._parser is not None
        assert protocol._parser.MAX_LENGTH == 64 * 1024
        # _limit_response_headers() overrides these on the instance.
        assert "lineReceived" in vars(protocol._parser)
        assert "lineLengthExceeded" in vars(protocol._parser)

    def test_refused_request_keeps_previous_parser_limits(self) -> None:
        """A request that Twisted refuses leaves the parser of the previous
        request untouched, so that its size counter is not reset while its
        response is still being read."""
        protocol = self._get_protocol()
        protocol.request(self._get_request())
        parser = protocol._parser
        assert parser is not None
        line_received = vars(parser)["lineReceived"]

        # A second request over the same connection is refused, as the first one
        # is still in progress.
        deferred = protocol.request(self._get_request())
        failures: list[Failure] = []
        deferred.addErrback(failures.append)

        assert len(failures) == 1
        assert failures[0].check(RequestNotSent)
        assert protocol._parser is parser
        assert vars(parser)["lineReceived"] is line_received
