import pytest
from twisted.internet import defer
from twisted.trial import unittest

from scrapy import Request, Spider, signals
from scrapy.utils.test import get_crawler, get_from_asyncio_queue
from tests.mockserver import MockServer


class ItemSpider(Spider):
    name = "itemspider"

    def start_requests(self):
        for index in range(10):
            yield Request(
                self.mockserver.url(f"/status?n=200&id={index}"), meta={"index": index}
            )

    def parse(self, response):
        return {"index": response.meta["index"]}


class TestAsyncSignal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    def setUp(self):
        self.items = []

    async def _on_item_scraped(self, item):
        item = await get_from_asyncio_queue(item)
        self.items.append(item)

    @pytest.mark.only_asyncio
    @defer.inlineCallbacks
    def test_simple_pipeline(self):
        crawler = get_crawler(ItemSpider)
        crawler.signals.connect(self._on_item_scraped, signals.item_scraped)
        yield crawler.crawl(mockserver=self.mockserver)
        assert len(self.items) == 10
        for index in range(10):
            assert {"index": index} in self.items
