"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from twisted.internet.protocol import Protocol
from twisted.python.failure import Failure

from scrapy import Spider
from scrapy.core.downloader.handlers.http11 import (
    HTTP11DownloadHandler,
    TunnelError,
    _TunnelingTCP4ClientEndpoint,
)
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from tests.test_downloader_handlers_http_base import (
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


def test_tunneling_endpoint_coalesced_bytes() -> None:
    reactor = MagicMock()
    context_factory = MagicMock()
    endpoint = _TunnelingTCP4ClientEndpoint(
        reactor=reactor,
        host="example.com",
        port=443,
        proxyConf=("proxy.example.com", 8080, None),
        contextFactory=context_factory,
    )
    endpoint._protocolFactory = MagicMock()

    protocol = Protocol()
    transport = MagicMock()
    protocol.transport = transport

    received: list[bytes] = []

    def mock_data_received(data: bytes) -> None:
        received.append(data)

    protocol.dataReceived = mock_data_received  # type: ignore[method-assign]

    endpoint.requestTunnel(protocol)

    coalesced_data = b"HTTP/1.1 200 Connection established\r\n\r\n\x16\x03\x01\x00\xfa"
    protocol.dataReceived(coalesced_data)

    assert received == [b"\x16\x03\x01\x00\xfa"]


def test_tunneling_endpoint_non_200_response() -> None:
    reactor = MagicMock()
    context_factory = MagicMock()
    endpoint = _TunnelingTCP4ClientEndpoint(
        reactor=reactor,
        host="example.com",
        port=443,
        proxyConf=("proxy.example.com", 8080, None),
        contextFactory=context_factory,
    )
    endpoint._protocolFactory = MagicMock()

    protocol = Protocol()
    transport = MagicMock()
    protocol.transport = transport

    received: list[bytes] = []

    def mock_data_received(data: bytes) -> None:
        received.append(data)

    protocol.dataReceived = mock_data_received  # type: ignore[method-assign]

    endpoint.requestTunnel(protocol)

    coalesced_data = b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n"
    protocol.dataReceived(coalesced_data)

    assert received == []
    assert endpoint._tunnelReadyDeferred.called
    failure = endpoint._tunnelReadyDeferred.result
    assert isinstance(failure, Failure)
    assert failure.check(TunnelError)
