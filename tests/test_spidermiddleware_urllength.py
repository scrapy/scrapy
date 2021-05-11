from unittest import TestCase

from testfixtures import LogCapture

from scrapy.spidermiddlewares.urllength import UrlLengthMiddleware
from scrapy.http import Response, Request
from scrapy.exceptions import NotConfigured
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from scrapy.settings import Settings


class TestUrlLengthMiddleware(TestCase):

    def setUp(self):
        self.short_url_req = Request('http://scrapytest.org/')
        self.long_url_req = Request('http://scrapytest.org/this_is_a_long_url')
        self.reqs = [self.short_url_req, self.long_url_req]
        self.response = Response('http://scrapytest.org')

    def generate_middleware_data(self, maxlength):
        result = dict()
        self.maxlength = maxlength
        self.settings = Settings({'URLLENGTH_LIMIT': maxlength})
        self.crawler = get_crawler(Spider)
        self.spider = self.crawler._create_spider('foo')
        self.stats = self.crawler.stats
        self.mw = UrlLengthMiddleware.from_settings(self.settings)
        return result

    def process_spider_output(self, maxlength):
        self.generate_middleware_data(maxlength)
        return list(self.mw.process_spider_output(self.response, self.reqs, self.spider))

    def test_middleware_works(self):
        self.assertEqual(self.process_spider_output(25), [self.short_url_req])

    def test_middleware_disabled(self):
        self.assertRaises(NotConfigured, self.process_spider_output, 0)

    def test_logging(self):
        with LogCapture() as log:
            self.process_spider_output(25)

        ric = self.stats.get_value('urllength/request_ignored_count', spider=self.spider)
        self.assertEqual(ric, 1)
        self.assertIn(f'Ignoring link (url length > {self.maxlength})', str(log))
