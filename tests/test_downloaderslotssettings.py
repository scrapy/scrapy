import time

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy import Request
from scrapy.core.downloader import Downloader, Slot
from scrapy.crawler import CrawlerRunner
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer
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

    async def start(self):
        self.times = {None: []}

        slots = [*self.custom_settings.get("DOWNLOAD_SLOTS", {}), None]

        for slot in slots:
            url = self.mockserver.url(f"/?downloader_slot={slot}")
            self.times[slot] = []
            yield Request(url, callback=self.parse, meta={"download_slot": slot})

    def parse(self, response):
        slot = response.meta.get("download_slot", None)
        self.times[slot].append(time.time())
        url = self.mockserver.url(f"/?downloader_slot={slot}&req=2")
        yield Request(url, callback=self.not_parse, meta={"download_slot": slot})

    def not_parse(self, response):
        slot = response.meta.get("download_slot", None)
        self.times[slot].append(time.time())


class CrawlTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    def setUp(self):
        self.runner = CrawlerRunner()

    @defer.inlineCallbacks
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
    crawler = get_crawler(settings_dict=settings)
    downloader = Downloader(crawler)
    downloader._slot_gc_loop.stop()  # Prevent an unclean reactor.
    request = Request("https://example.com")
    _, actual = downloader._get_slot(request, spider=None)
    expected = Slot(**params)
    for param in params:
        assert getattr(expected, param) == getattr(actual, param), (
            f"Slot.{param}: {getattr(expected, param)!r} != {getattr(actual, param)!r}"
        )
