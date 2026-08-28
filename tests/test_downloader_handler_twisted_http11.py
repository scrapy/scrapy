"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Request, Spider
from scrapy.core.downloader.contextfactory import _load_context_factory_from_settings
from scrapy.core.downloader.handlers.http11 import (
    HTTP11DownloadHandler,
    _ScrapyAgent,
    _TunnelingAgent,
)
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import build_from_crawler
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
        build_from_crawler(HTTP11DownloadHandler, crawler)


@pytest.mark.parametrize(
    ("proxy_headers", "proxy_auth", "expected"),
    [
        (None, None, ()),
        ({"X-B": "2", "X-A": "1"}, None, (("X-A", "1"), ("X-B", "2"))),
        (None, "Basic Zm9v", (("Proxy-Authorization", "Basic Zm9v"),)),
        (
            {"X-A": "1"},
            "Basic Zm9v",
            (("Proxy-Authorization", "Basic Zm9v"), ("X-A", "1")),
        ),
        (
            {"Proxy-Authorization": "Custom foo"},
            "Basic Zm9v",
            (("Proxy-Authorization", "Custom foo"),),
        ),
    ],
    ids=[
        "no headers",
        "sorted headers",
        "auth header",
        "auth header and headers",
        "auth header overridden",
    ],
)
def test_tunnel_proxy_headers(
    proxy_headers: dict[str, str] | None,
    proxy_auth: str | None,
    expected: tuple[tuple[str, str], ...],
) -> None:
    meta: dict[str, Any] = {"proxy": "http://proxy.example:8080"}
    if proxy_headers is not None:
        meta["proxy_headers"] = proxy_headers
    request = Request(
        "https://example.com",
        meta=meta,
        headers={"Proxy-Authorization": proxy_auth} if proxy_auth else None,
    )
    crawler = get_crawler(Spider)
    agent = _ScrapyAgent(
        contextFactory=_load_context_factory_from_settings(crawler), crawler=crawler
    )
    tunneling_agent = agent._get_agent(request, 10)
    assert isinstance(tunneling_agent, _TunnelingAgent)
    assert tunneling_agent._proxyConf == ("proxy.example", 8080, expected)


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
