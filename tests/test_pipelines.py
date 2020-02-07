import asyncio

from pytest import mark
from twisted.internet import defer
from twisted.internet.defer import Deferred
from twisted.trial import unittest

from scrapy import Spider, signals, Request
from scrapy.utils.test import get_crawler, get_from_asyncio_queue

from tests.mockserver import MockServer


class SimplePipeline:
    def process_item(self, item, spider):
        item['pipeline_passed'] = True
        return item


class DeferredPipeline:
    def cb(self, item):
        item['pipeline_passed'] = True
        return item

    def process_item(self, item, spider):
        d = Deferred()
        d.addCallback(self.cb)
        d.callback(item)
        return d


class AsyncDefPipeline:
    async def process_item(self, item, spider):
        await defer.succeed(42)
        item['pipeline_passed'] = True
        return item


class AsyncDefAsyncioPipeline:
    async def process_item(self, item, spider):
        await asyncio.sleep(0.2)
        item['pipeline_passed'] = await get_from_asyncio_queue(True)
        return item


class OrderPipeline:
    name = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self.crawler = crawler

    def open_spider(self, spider):
        self.crawler.call_list.append(('open_spider', self.name))

    def process_item(self, item, spider):
        self.crawler.call_list.append(('process_item', self.name))
        return item

    def close_spider(self, spider):
        self.crawler.call_list.append(('close_spider', self.name))


class Pipeline1(OrderPipeline):
    name = '1'


class Pipeline2(OrderPipeline):
    name = '2'


class ItemSpider(Spider):
    name = 'itemspider'

    def start_requests(self):
        yield Request(self.mockserver.url('/status?n=200'))

    def parse(self, response):
        return {'field': 42}


class PipelineTestCase(unittest.TestCase):
    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    def _on_item_scraped(self, item):
        self.assertIsInstance(item, dict)
        self.assertTrue(item.get('pipeline_passed'))
        self.items.append(item)

    def _create_crawler(self, *pipeline_classes, **extra_settings):
        settings = {
            'ITEM_PIPELINES': {
                __name__ + '.' + pipeline_class.__name__: value
                for value, pipeline_class in
                enumerate(pipeline_classes, start=1)
            },
            **extra_settings,
        }
        crawler = get_crawler(ItemSpider, settings)
        crawler.signals.connect(self._on_item_scraped, signals.item_scraped)
        self.items = []
        return crawler

    @defer.inlineCallbacks
    def test_simple_pipeline(self):
        crawler = self._create_crawler(SimplePipeline)
        yield crawler.crawl(mockserver=self.mockserver)
        self.assertEqual(len(self.items), 1)

    @defer.inlineCallbacks
    def test_deferred_pipeline(self):
        crawler = self._create_crawler(DeferredPipeline)
        yield crawler.crawl(mockserver=self.mockserver)
        self.assertEqual(len(self.items), 1)

    @defer.inlineCallbacks
    def test_asyncdef_pipeline(self):
        crawler = self._create_crawler(AsyncDefPipeline)
        yield crawler.crawl(mockserver=self.mockserver)
        self.assertEqual(len(self.items), 1)

    @mark.only_asyncio()
    @defer.inlineCallbacks
    def test_asyncdef_asyncio_pipeline(self):
        crawler = self._create_crawler(AsyncDefAsyncioPipeline)
        yield crawler.crawl(mockserver=self.mockserver)
        self.assertEqual(len(self.items), 1)

    @defer.inlineCallbacks
    def test_pipeline_method_order(self):
        expected_call_list = [
            ('open_spider', '1'),
            ('open_spider', '2'),
            ('process_item', '1'),
            ('process_item', '2'),
            ('close_spider', '1'),
            ('close_spider', '2'),
        ]
        crawler = self._create_crawler(Pipeline1, Pipeline2)
        crawler.call_list = []
        yield crawler.crawl(mockserver=self.mockserver)
        self.assertEqual(crawler.call_list, expected_call_list)
