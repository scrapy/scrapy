import time
from typing import Any

import pytest

from scrapy import Request
from scrapy.core.downloader import Downloader, Slot
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Response
from scrapy.spiders import Spider
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.spiders import MetaSpider
from tests.utils.decorators import coroutine_test, inline_callbacks_test


class _RedirectSlotDownloadHandler:
    lazy = False

    async def download_request(self, request: Request) -> Response:
        if request.url == "http://a.example/":
            return Response(
                request.url,
                status=302,
                headers={"Location": "http://b.example/"},
                request=request,
            )
        return Response(request.url, request=request)


class CrossDomainRedirectSpider(Spider):
    name = "cross_domain_redirect"
    custom_settings = {
        "DOWNLOAD_HANDLERS": {"http": _RedirectSlotDownloadHandler},
    }

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.slots: list[str] = []
        self.auto_flag: object = None

    async def start(self):
        yield Request("http://a.example/", callback=self.parse)

    def parse(self, response: Response):
        self.slots.append(response.meta["download_slot"])
        self.auto_flag = response.meta.get("_auto_download_slot")


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
        assert self.mockserver
        self.default_slot = self.mockserver.host
        self.times: dict[str, list[float]] = {}

    async def start(self):
        assert self.mockserver
        slots = [*self.custom_settings.get("DOWNLOAD_SLOTS", {}), None]
        for slot in slots:
            url = self.mockserver.url(f"/?downloader_slot={slot}")
            self.times[slot or self.default_slot] = []
            yield Request(url, callback=self.parse, meta={"download_slot": slot})

    def parse(self, response):
        assert self.mockserver
        slot = response.meta.get("download_slot", self.default_slot)
        self.times[slot].append(time.time())
        url = self.mockserver.url(f"/?downloader_slot={slot}&req=2")
        yield Request(url, callback=self.not_parse, meta={"download_slot": slot})

    def not_parse(self, response):
        slot = response.meta.get("download_slot", self.default_slot)
        self.times[slot].append(time.time())


class NoDelayDownloaderSlotsSpider(DownloaderSlotsSettingsTestSpider):
    custom_settings = {
        "DOWNLOAD_SLOTS": {
            slot: {}
            for slot in DownloaderSlotsSettingsTestSpider.custom_settings[
                "DOWNLOAD_SLOTS"
            ]
        },
    }


class FollowFromResponseMetaSpider(MetaSpider):
    name = "follow_from_response_meta"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.slots: list[str] = []
        self.auto_flags: list[bool] = []

    async def start(self):
        assert self.mockserver
        yield Request(self.mockserver.url("/text"), callback=self.parse)

    def parse(self, response: Response):
        self.auto_flags.append("_auto_download_slot" in response.meta)
        meta = dict(response.meta)
        meta["download_slot"] = "custom"
        yield Request(
            response.url, callback=self.not_parse, meta=meta, dont_filter=True
        )

    def not_parse(self, response: Response):
        self.slots.append(response.meta["download_slot"])
        self.auto_flags.append("_auto_download_slot" in response.meta)


@inline_callbacks_test
def test_delay(mockserver: MockServer):
    crawler = get_crawler(DownloaderSlotsSettingsTestSpider)
    yield crawler.crawl(mockserver=mockserver)
    assert isinstance(crawler.spider, DownloaderSlotsSettingsTestSpider)
    slots = crawler.engine.downloader.slots
    times = crawler.spider.times
    # Downloading and processing a response add a roughly constant amount
    # of time on top of the configured delay, so the margin is absolute.
    # It stays well below the 1 second that separates the delays being
    # compared, so a slot using the delay of another one still fails.
    tolerance = 0.75

    for slot, (first, second) in times.items():
        assert abs((second - first) - slots[slot].delay) < tolerance


@inline_callbacks_test
def test_redirect_to_other_host_changes_slot():
    crawler = get_crawler(CrossDomainRedirectSpider)
    yield crawler.crawl()
    assert isinstance(crawler.spider, CrossDomainRedirectSpider)
    assert crawler.spider.slots == ["b.example"]
    assert crawler.spider.auto_flag is None


@inline_callbacks_test
def test_user_slot_from_response_meta_is_kept(mockserver: MockServer):
    crawler = get_crawler(FollowFromResponseMetaSpider)
    yield crawler.crawl(mockserver=mockserver)
    assert isinstance(crawler.spider, FollowFromResponseMetaSpider)
    assert crawler.spider.auto_flags == [False, False]
    assert crawler.spider.slots == ["custom"]


@coroutine_test
async def test_params():
    params: dict[str, Any] = {
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
    request = Request("https://example.com")
    _, actual = downloader._get_slot(request)
    downloader.close()
    expected = Slot(**params)
    for param in params:
        assert getattr(expected, param) == getattr(actual, param), (
            f"Slot.{param}: {getattr(expected, param)!r} != {getattr(actual, param)!r}"
        )


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
    assert slot1 == slot2


@pytest.mark.parametrize(
    "priority_queue_class",
    [
        "scrapy.pqueues.ScrapyPriorityQueue",
        "scrapy.pqueues.DownloaderAwarePriorityQueue",
    ],
)
@coroutine_test
async def test_none_slot_with_priority_queue(
    mockserver: MockServer, priority_queue_class: str
) -> None:
    """Test specific cases for None slot handling with different priority queues."""
    crawler = get_crawler(
        NoDelayDownloaderSlotsSpider,
        settings_dict={"SCHEDULER_PRIORITY_QUEUE": priority_queue_class},
    )
    await crawler.crawl_async(mockserver=mockserver)
    assert isinstance(crawler.spider, NoDelayDownloaderSlotsSpider)

    assert hasattr(crawler.spider, "times")
    assert None not in crawler.spider.times
    assert crawler.spider.default_slot in crawler.spider.times
    assert len(crawler.spider.times[crawler.spider.default_slot]) == 2

    stats = crawler.stats
    assert stats.get_value("spider_exceptions", 0) == 0
    assert stats.get_value("downloader/exception_count", 0) == 0
