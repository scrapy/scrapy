from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.signals import request_left_downloader
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from tests.utils.decorators import inline_callbacks_test

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.crawler import Crawler
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


@inline_callbacks_test
def test_success(mockserver: MockServer):
    crawler = get_crawler(SignalCatcherSpider)
    yield crawler.crawl(mockserver.url("/status?n=200"))
    assert isinstance(crawler.spider, SignalCatcherSpider)
    assert crawler.spider.caught_times == 1


@inline_callbacks_test
def test_timeout(mockserver: MockServer):
    crawler = get_crawler(SignalCatcherSpider, {"DOWNLOAD_TIMEOUT": 0.1})
    yield crawler.crawl(mockserver.url("/delay?n=0.2"))
    assert isinstance(crawler.spider, SignalCatcherSpider)
    assert crawler.spider.caught_times == 1


@inline_callbacks_test
def test_disconnect(mockserver: MockServer):
    crawler = get_crawler(SignalCatcherSpider)
    yield crawler.crawl(mockserver.url("/drop"))
    assert isinstance(crawler.spider, SignalCatcherSpider)
    assert crawler.spider.caught_times == 1


@inline_callbacks_test
def test_noconnect():
    crawler = get_crawler(SignalCatcherSpider)
    yield crawler.crawl("http://thereisdefinetelynosuchdomain.com")
    assert isinstance(crawler.spider, SignalCatcherSpider)
    assert crawler.spider.caught_times == 1
