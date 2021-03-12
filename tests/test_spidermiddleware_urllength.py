from unittest import TestCase

from testfixtures import LogCapture

from scrapy.spidermiddlewares.urllength import UrlLengthMiddleware
from scrapy.http import Response, Request
from scrapy.spiders import Spider
from scrapy.statscollectors import StatsCollector
from scrapy.utils.test import get_crawler


class TestUrlLengthMiddleware(TestCase):

    def setUp(self):
        crawler = get_crawler(Spider)
        self.spider = crawler._create_spider('foo')

        self.stats = StatsCollector(crawler)
        self.stats.open_spider(self.spider)

        self.maxlength = 25
        self.mw = UrlLengthMiddleware(maxlength=self.maxlength, stats=self.stats)

        self.response = Response('http://scrapytest.org')
        self.short_url_req = Request('http://scrapytest.org/')
        self.long_url_req = Request('http://scrapytest.org/this_is_a_long_url')
        self.reqs = [self.short_url_req, self.long_url_req]

    def tearDown(self):
        self.stats.close_spider(self.spider, '')

    def process_spider_output(self):
        return list(self.mw.process_spider_output(self.response, self.reqs, self.spider))

    def test_middleware_works(self):
        self.assertEqual(self.process_spider_output(), [self.short_url_req])

    def test_logging(self):
        with LogCapture() as log:
            self.process_spider_output()

        ric = self.stats.get_value('urllength/request_ignored_count', spider=self.spider)
        self.assertEqual(ric, 1)

        self.assertIn(f'Ignoring link (url length > {self.maxlength})', str(log))
