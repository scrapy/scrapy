import time
from typing import Any

import pytest
from twisted.internet.defer import inlineCallbacks

from scrapy import Request
from scrapy.core.downloader import Downloader, Slot
from scrapy.crawler import CrawlerRunner
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.spiders import MetaSpider


class DownloaderSlotsSettingsTestSpider(MetaSpider):
    name = "downloader_slots"

    custom_settings = {
        "DOWNLOAD_DELAY": 1,
        "RANDOMIZE_DOWNLOAD_DELAY": False,
        "DOWNLOAD_SLOTS": {
            "quotes.toscrape.com": {
                "concurrency": 1,
                "delay": 2,
                "randomize_delay": False,
                "throttle": False,
            },
            "books.toscrape.com": {"delay": 3, "randomize_delay": False},
        },
    }

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.default_slot = self.mockserver.host
        self.times: dict[str, list[float]] = {}

    async def start(self):
        slots = [*self.custom_settings.get("DOWNLOAD_SLOTS", {}), None]
        for slot in slots:
            url = self.mockserver.url(f"/?downloader_slot={slot}")
            self.times[slot or self.default_slot] = []
            yield Request(url, callback=self.parse, meta={"download_slot": slot})

    def parse(self, response):
        slot = response.meta.get("download_slot", self.default_slot)
        self.times[slot].append(time.time())
        url = self.mockserver.url(f"/?downloader_slot={slot}&req=2")
        yield Request(url, callback=self.not_parse, meta={"download_slot": slot})

    def not_parse(self, response):
        slot = response.meta.get("download_slot", self.default_slot)
        self.times[slot].append(time.time())


class TestCrawl:
    @classmethod
    def setup_class(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def teardown_class(cls):
        cls.mockserver.__exit__(None, None, None)

    def setup_method(self):
        self.runner = CrawlerRunner()

    @inlineCallbacks
    def test_delay(self):
        crawler = get_crawler(DownloaderSlotsSettingsTestSpider)
        yield crawler.crawl(mockserver=self.mockserver)
        slots = crawler.engine.downloader.slots
        times = crawler.spider.times
        tolerance = 0.3

        delays_real = {k: v[1] - v[0] for k, v in times.items()}
        error_delta = {
            k: 1 - min(delays_real[k], v.delay) / max(delays_real[k], v.delay)
            for k, v in slots.items()
        }

        assert max(list(error_delta.values())) < tolerance


def test_params():
    params = {
        "concurrency": 1,
        "delay": 2,
        "randomize_delay": False,
    }
    settings = {
        "DOWNLOAD_SLOTS": {
            "example.com": params,
        },
    }
    crawler = get_crawler(DefaultSpider, settings_dict=settings)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    downloader._slot_gc_loop.stop()  # Prevent an unclean reactor.
    request = Request("https://example.com")
    _, actual = downloader._get_slot(request)
    expected = Slot(**params)
    for param in params:
        assert getattr(expected, param) == getattr(actual, param), (
            f"Slot.{param}: {getattr(expected, param)!r} != {getattr(actual, param)!r}"
        )


def test_get_slot_deprecated_spider_arg():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    downloader._slot_gc_loop.stop()  # Prevent an unclean reactor.
    request = Request("https://example.com")

    with pytest.warns(
        ScrapyDeprecationWarning,
        match=r"Passing a 'spider' argument to Downloader\._get_slot\(\) is deprecated",
    ):
        key1, slot1 = downloader._get_slot(request, spider=crawler.spider)
    key2, slot2 = downloader._get_slot(request)

    assert key1 == key2
    assert slot1 == slot2


@pytest.mark.parametrize(
    "priority_queue_class",
    [
        "scrapy.pqueues.ScrapyPriorityQueue",
        "scrapy.pqueues.DownloaderAwarePriorityQueue",
    ],
)
@deferred_f_from_coro_f
async def test_none_slot_with_priority_queue(
    mockserver: MockServer, priority_queue_class: str
) -> None:
    """Test specific cases for None slot handling with different priority queues."""
    crawler = get_crawler(
        DownloaderSlotsSettingsTestSpider,
        settings_dict={"SCHEDULER_PRIORITY_QUEUE": priority_queue_class},
    )
    await crawler.crawl_async(mockserver=mockserver)
    assert isinstance(crawler.spider, DownloaderSlotsSettingsTestSpider)

    assert hasattr(crawler.spider, "times")
    assert None not in crawler.spider.times
    assert crawler.spider.default_slot in crawler.spider.times
    assert len(crawler.spider.times[crawler.spider.default_slot]) == 2

    assert crawler.stats
    stats = crawler.stats
    assert stats.get_value("spider_exceptions", 0) == 0
    assert stats.get_value("downloader/exception_count", 0) == 0
