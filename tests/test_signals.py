from pytest import mark
from twisted.internet import defer
from twisted.trial import unittest

from scrapy import signals, Request, Spider
from scrapy.utils.test import get_crawler, get_from_asyncio_queue

from tests.mockserver import MockServer


class ItemSpider(Spider):
    name = 'itemspider'

    def start_requests(self):
        for index in range(10):
            yield Request(self.mockserver.url('/status?n=200&id=%d' % index),
                          meta={'index': index})

    def parse(self, response):
        return {'index': response.meta['index']}


class AsyncSignalTestCase(unittest.TestCase):
    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()
        self.items = []

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    async def _on_item_scraped(self, item):
        item = await get_from_asyncio_queue(item)
        self.items.append(item)

    @mark.only_asyncio()
    @defer.inlineCallbacks
    def test_simple_pipeline(self):
        crawler = get_crawler(ItemSpider)
        crawler.signals.connect(self._on_item_scraped, signals.item_scraped)
        yield crawler.crawl(mockserver=self.mockserver)
        self.assertEqual(len(self.items), 10)
        for index in range(10):
            self.assertIn({'index': index}, self.items)
