"""Tests for scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pytest
from twisted.internet.defer import DeferredList

try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]

from scrapy import Spider
from scrapy.core.downloader.handlers._base_http import _auto_connection_limit
from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http import Request
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
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
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from scrapy.core.downloader.handlers import DownloadHandlerProtocol
    from tests.mockserver.http import MockServer


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


@asynccontextmanager
async def _get_dh(
    settings_dict: dict[str, Any],
) -> AsyncGenerator[HTTP11DownloadHandler]:
    crawler = get_crawler(DefaultSpider, settings_dict)
    crawler.spider = crawler._create_spider()
    dh = build_from_crawler(HTTP11DownloadHandler, crawler)
    try:
        yield dh
    finally:
        await dh.close()


@coroutine_test
async def test_connection_limit_auto() -> None:
    async with _get_dh({}) as dh:
        assert dh._pool._limit == _auto_connection_limit()


@coroutine_test
@pytest.mark.parametrize("limit", [0, 20])
async def test_connection_limit_explicit(limit: int) -> None:
    async with _get_dh({"CONCURRENT_CONNECTIONS_PER_HANDLER": limit}) as dh:
        assert dh._pool._limit == limit


@coroutine_test
async def test_connection_limit_below_concurrent_requests(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings_dict = {
        "CONCURRENT_CONNECTIONS_PER_HANDLER": 4,
        "CONCURRENT_REQUESTS": 8,
    }
    with caplog.at_level("WARNING"):
        async with _get_dh(settings_dict):
            pass
    assert "CONCURRENT_CONNECTIONS_PER_HANDLER (4)" in caplog.text


@pytest.mark.skipif(resource is None, reason="No file descriptor limit")
@coroutine_test
async def test_connection_limit_auto_without_file_descriptor_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    infinity = resource.RLIM_INFINITY
    monkeypatch.setattr(resource, "getrlimit", lambda _: (infinity, infinity))
    async with _get_dh({}) as dh:
        assert dh._pool._limit == 0


@coroutine_test
async def test_connection_limit_with_several_connections_per_host(
    mockserver: MockServer,
) -> None:
    url = mockserver.url("/connection-id")
    slow_url = mockserver.url("/connection-id?delay=0.5")
    other_url = url.replace("127.0.0.1", "localhost")
    async with _get_dh({"CONCURRENT_CONNECTIONS_PER_HANDLER": 2}) as dh:
        results = await maybe_deferred_to_future(
            DeferredList(
                [
                    deferred_from_coro(dh.download_request(Request(slow_url)))
                    for _ in range(2)
                ],
                fireOnOneErrback=True,
            )
        )
        ids = {response.text for _, response in results}
        assert len(ids) == 2
        # only one of the two connections to the host makes room for the
        # connection to the other host, so the other one stays reusable
        await dh.download_request(Request(other_url))
        reused = await dh.download_request(Request(url))
    assert reused.text in ids


@coroutine_test
async def test_keepalive_timeout() -> None:
    async with _get_dh({"CONNECTION_KEEPALIVE_TIMEOUT": 5}) as dh:
        assert dh._pool.cachedConnectionTimeout == 5


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
