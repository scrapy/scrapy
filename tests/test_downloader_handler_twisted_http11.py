"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, cast

import pytest
from twisted.internet.error import ConnectingCancelledError
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.testing import MemoryReactorClock
from twisted.python.failure import Failure

from scrapy import Spider
from scrapy.core.downloader.contextfactory import _load_context_factory_from_settings
from scrapy.core.downloader.handlers.http11 import (
    HTTP11DownloadHandler,
    _TunnelingTCP4ClientEndpoint,
)
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.utils.test import get_crawler
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
    from twisted.internet.base import ReactorBase

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


def test_tunneling_cancelled_before_connected() -> None:
    """Cancelling a tunneled download before the connection to the proxy is
    established stops the connection attempt.

    A download cannot reach this scenario, because the connection timeout of
    the endpoint, which uses the same value as the download timeout, always
    fires earlier than the cancellation. See also
    ``test_download_with_proxy_stalled_connect``, which covers cancelling once
    the connection to the proxy is established.
    """
    reactor = MemoryReactorClock()
    endpoint = _TunnelingTCP4ClientEndpoint(
        reactor=cast("ReactorBase", reactor),
        host="example.com",
        port=443,
        proxyConf=("127.0.0.1", 8080, None),
        contextFactory=_load_context_factory_from_settings(get_crawler()),
        timeout=30,
    )
    results: list[Protocol | Failure] = []
    endpoint.connect(Factory()).addBoth(results.append)

    endpoint._tunnelReadyDeferred.cancel()

    assert reactor.connectors[0].stoppedConnecting
    assert isinstance(results[0], Failure)
    assert isinstance(results[0].value, ConnectingCancelledError)


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
