from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from scrapy.signals import (
    request_left_downloader,
    request_reached_downloader,
    response_downloaded,
)
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from tests.mockserver.http import MockServer


class SignalCatcherSpider(Spider):
    name = "signal_catcher"

    def __init__(self, crawler: Crawler, url: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        crawler.signals.connect(self.on_request_left, signal=request_left_downloader)
        self.caught_times = 0
        self.start_urls = [url]

    @classmethod
    def from_crawler(
        cls, crawler: Crawler, *args: Any, **kwargs: Any
    ) -> SignalCatcherSpider:
        return cls(crawler, *args, **kwargs)

    def on_request_left(self, request: Request, spider: Spider) -> None:
        self.caught_times += 1


@coroutine_test
async def test_success(mockserver: MockServer) -> None:
    crawler = get_crawler(SignalCatcherSpider)
    await crawler.crawl_async(mockserver.url("/status?n=200"))
    assert isinstance(crawler.spider, SignalCatcherSpider)
    assert crawler.spider.caught_times == 1


@coroutine_test
async def test_timeout(mockserver: MockServer) -> None:
    crawler = get_crawler(SignalCatcherSpider, {"DOWNLOAD_TIMEOUT": 0.1})
    await crawler.crawl_async(mockserver.url("/delay?n=0.2"))
    assert isinstance(crawler.spider, SignalCatcherSpider)
    assert crawler.spider.caught_times == 1


@coroutine_test
async def test_disconnect(mockserver: MockServer) -> None:
    crawler = get_crawler(SignalCatcherSpider)
    await crawler.crawl_async(mockserver.url("/drop"))
    assert isinstance(crawler.spider, SignalCatcherSpider)
    assert crawler.spider.caught_times == 1


@coroutine_test
async def test_noconnect() -> None:
    crawler = get_crawler(SignalCatcherSpider)
    await crawler.crawl_async("http://thereisdefinetelynosuchdomain.com")
    assert isinstance(crawler.spider, SignalCatcherSpider)
    assert crawler.spider.caught_times == 1


@coroutine_test
async def test_async_handlers(mockserver: MockServer) -> None:
    """The downloader signals wait for asynchronous handlers."""
    events: list[str] = []

    async def on_reached(request: Request, spider: Spider) -> None:
        await asyncio.sleep(0.01)
        events.append("reached")

    async def on_downloaded(
        response: Response, request: Request, spider: Spider
    ) -> None:
        await asyncio.sleep(0.01)
        events.append("downloaded")

    async def on_left(request: Request, spider: Spider) -> None:
        await asyncio.sleep(0.01)
        events.append("left")

    crawler = get_crawler(SignalCatcherSpider)
    crawler.signals.connect(on_reached, signal=request_reached_downloader)
    crawler.signals.connect(on_downloaded, signal=response_downloaded)
    crawler.signals.connect(on_left, signal=request_left_downloader)
    await crawler.crawl_async(mockserver.url("/status?n=200"))
    assert events == ["reached", "downloaded", "left"]
