from twisted.internet import defer
from twisted.internet.defer import Deferred
from twisted.trial import unittest

from scrapy import Spider, signals, Request
from scrapy.utils.test import get_crawler

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

    def _create_crawler(self, pipeline_class):
        settings = {
            'ITEM_PIPELINES': {__name__ + '.' + pipeline_class.__name__: 1},
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
