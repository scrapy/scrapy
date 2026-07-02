from typing import Any
from urllib.parse import urlparse

import pytest

from scrapy import Request
from scrapy.core.downloader import Downloader
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.spiders import MetaSpider
from tests.utils.decorators import coroutine_test


class DownloaderSlotsSettingsTestSpider(MetaSpider):
    name = "downloader_slots"

    custom_settings = {
        "DOWNLOAD_SLOTS": {
            "quotes.toscrape.com": {"concurrency": 1},
            "books.toscrape.com": {"concurrency": 2},
        },
    }

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        assert self.mockserver
        self.default_slot = urlparse(self.mockserver.url("/")).netloc
        self.times: dict[str, list[float]] = {}

    async def start(self):
        slots = [*self.custom_settings.get("DOWNLOAD_SLOTS", {}), None]
        for slot in slots:
            url = self.mockserver.url(f"/?downloader_slot={slot}")
            self.times[slot or self.default_slot] = []
            yield Request(url, callback=self.parse, meta={"download_slot": slot})

    def parse(self, response):
        slot = response.meta.get("download_slot", self.default_slot)
        self.times[slot].append(response.meta.get("download_latency"))
        url = self.mockserver.url(f"/?downloader_slot={slot}&req=2")
        yield Request(url, callback=self.not_parse, meta={"download_slot": slot})

    def not_parse(self, response):
        slot = response.meta.get("download_slot", self.default_slot)
        self.times[slot].append(response.meta.get("download_latency"))


@coroutine_test
async def test_concurrency_key_deprecated():
    settings = {"DOWNLOAD_SLOTS": {"example.com": {"concurrency": 3}}}
    crawler = get_crawler(DefaultSpider, settings_dict=settings)
    crawler.spider = crawler._create_spider()
    with pytest.warns(ScrapyDeprecationWarning) as warns:
        downloader = Downloader(crawler)
    messages = [str(w.message) for w in warns]
    assert any("DOWNLOAD_SLOTS setting is deprecated" in m for m in messages)
    assert any("'concurrency' key in DOWNLOAD_SLOTS" in m for m in messages)
    downloader._get_slot(Request("https://example.com"))
    downloader.close()


@coroutine_test
async def test_download_slots_deprecated():
    settings = {"DOWNLOAD_SLOTS": {"example.com": {"concurrency": 2}}}
    crawler = get_crawler(DefaultSpider, settings_dict=settings)
    crawler.spider = crawler._create_spider()
    with pytest.warns(
        ScrapyDeprecationWarning, match="DOWNLOAD_SLOTS setting is deprecated"
    ):
        Downloader(crawler).close()


@coroutine_test
async def test_slots_deprecated():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    request = Request("https://example.com")
    request.meta[Downloader.DOWNLOAD_SLOT] = "example.com"
    downloader.active.add(request)
    with pytest.warns(ScrapyDeprecationWarning, match="Downloader.slots is deprecated"):
        slot = downloader.slots.get("example.com")
    assert slot is not None
    assert isinstance(slot.active, set)
    assert request in slot.active
    downloader.active.discard(request)
    downloader.close()


@coroutine_test
async def test_download_slot_meta_deprecated():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    request = Request("https://example.com")
    request.meta["download_slot"] = "custom"
    with pytest.warns(
        ScrapyDeprecationWarning, match="'download_slot' request meta key is deprecated"
    ):
        key, _ = downloader._get_slot(request)
    downloader.close()
    assert key == "custom"


@coroutine_test
async def test_delay_deprecated():
    settings = {
        "DOWNLOAD_SLOTS": {"example.com": {"delay": 2, "randomize_delay": False}}
    }
    crawler = get_crawler(DefaultSpider, settings_dict=settings)
    crawler.spider = crawler._create_spider()
    with pytest.warns(ScrapyDeprecationWarning) as warns:
        downloader = Downloader(crawler)
    messages = [str(w.message) for w in warns]
    assert any("DOWNLOAD_SLOTS setting is deprecated" in m for m in messages)
    assert any("'delay' key in DOWNLOAD_SLOTS" in m for m in messages)
    downloader._get_slot(Request("https://example.com"))
    downloader.close()


@coroutine_test
async def test_get_slot_deprecated_spider_arg():
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    request = Request("https://example.com")

    with pytest.warns(
        ScrapyDeprecationWarning,
        match=r"Passing a 'spider' argument to Downloader\._get_slot\(\) is deprecated",
    ):
        key1, slot1 = downloader._get_slot(request, spider=crawler.spider)
    key2, slot2 = downloader._get_slot(request)
    downloader.close()

    assert key1 == key2
    assert slot1._key == slot2._key


@pytest.mark.parametrize(
    "priority_queue_class",
    [
        "scrapy.pqueues.ScrapyPriorityQueue",
        "scrapy.pqueues.DownloaderAwarePriorityQueue",
    ],
)
@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
@coroutine_test
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
