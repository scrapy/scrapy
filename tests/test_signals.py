from twisted.internet import defer
from twisted.trial import unittest

from scrapy import signals, Request, Spider
from scrapy.utils.test import get_crawler

from tests.mockserver import MockServer


class ItemSpider(Spider):
    name = 'itemspider'

    def start_requests(self):
        for _ in range(10):
            yield Request(self.mockserver.url('/status?n=200'),
                          dont_filter=True)

    def parse(self, response):
        return {'field': 42}


class AsyncSignalTestCase(unittest.TestCase):
    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()
        self.items = []

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    async def _on_item_scraped(self, item):
        self.items.append(item)

    @defer.inlineCallbacks
    def test_simple_pipeline(self):
        crawler = get_crawler(ItemSpider)
        crawler.signals.connect(self._on_item_scraped, signals.item_scraped)
        yield crawler.crawl(mockserver=self.mockserver)
        self.assertEqual(len(self.items), 10)
