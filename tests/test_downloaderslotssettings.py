import time

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy.crawler import CrawlerRunner
from scrapy.http import Request
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
            },
            "books.toscrape.com": {"delay": 3, "randomize_delay": False},
        },
    }

    def start_requests(self):
        self.times = {None: []}

        slots = list(self.custom_settings.get("DOWNLOAD_SLOTS", {}).keys()) + [None]

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
    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()
        self.runner = CrawlerRunner()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_delay(self):
        crawler = CrawlerRunner().create_crawler(DownloaderSlotsSettingsTestSpider)
        yield crawler.crawl(mockserver=self.mockserver)
        slots = crawler.engine.downloader.slots
        times = crawler.spider.times
        tolerance = 0.3

        delays_real = {k: v[1] - v[0] for k, v in times.items()}
        error_delta = {
            k: 1 - min(delays_real[k], v.delay) / max(delays_real[k], v.delay)
            for k, v in slots.items()
        }

        self.assertTrue(max(list(error_delta.values())) < tolerance)
