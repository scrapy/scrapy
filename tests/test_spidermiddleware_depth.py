from unittest import TestCase

from scrapy.spidermiddlewares.depth import DepthMiddleware
from scrapy.http import Response, Request
from scrapy.spiders import Spider
from scrapy.statscollectors import StatsCollector
from scrapy.utils.test import get_crawler


class TestDepthMiddleware(TestCase):

    def setUp(self):
        crawler = get_crawler(Spider)
        self.spider = crawler._create_spider('scrapytest.org')

        self.stats = StatsCollector(crawler)
        self.stats.open_spider(self.spider)

        self.mw = DepthMiddleware(1, self.stats, True)

    def test_process_spider_output(self):
        req = Request('http://scrapytest.org')
        resp = Response('http://scrapytest.org')
        resp.request = req
        result = [Request('http://scrapytest.org')]

        out = list(self.mw.process_spider_output(resp, result, self.spider))
        self.assertEqual(out, result)

        rdc = self.stats.get_value('request_depth_count/1', spider=self.spider)
        self.assertEqual(rdc, 1)

        req.meta['depth'] = 1

        out2 = list(self.mw.process_spider_output(resp, result, self.spider))
        self.assertEqual(out2, [])

        rdm = self.stats.get_value('request_depth_max', spider=self.spider)
        self.assertEqual(rdm, 1)

    def tearDown(self):
        self.stats.close_spider(self.spider, '')
