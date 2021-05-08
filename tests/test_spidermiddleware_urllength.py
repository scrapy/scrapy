from unittest import TestCase

from testfixtures import LogCapture

from scrapy.spidermiddlewares.urllength import UrlLengthMiddleware
from scrapy.http import Response, Request
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from scrapy.settings import Settings


class TestUrlLengthMiddleware(TestCase):

    def setUp(self):
        self.maxlength = 25
        settings = Settings({'URLLENGTH_LIMIT': self.maxlength})

        crawler = get_crawler(Spider)
        self.spider = crawler._create_spider('foo')
        self.stats = crawler.stats
        self.mw = UrlLengthMiddleware.from_settings(settings)

        self.maxlength_negative = -1
        settings_negative = Settings({'URLLENGTH_LIMIT': self.maxlength_negative})

        crawler_negative = get_crawler(Spider)
        self.spider_negative = crawler_negative._create_spider('foo_negative')
        self.stats_negative = crawler_negative.stats
        self.mw_negative = UrlLengthMiddleware.from_settings(settings_negative)
        self.response = Response('http://scrapytest.org')

        self.short_url_req = Request('http://scrapytest.org/')
        self.long_url_req = Request('http://scrapytest.org/this_is_a_long_url')
        self.reqs = [self.short_url_req, self.long_url_req]

    def process_spider_output(self):
        return list(self.mw.process_spider_output(self.response, self.reqs, self.spider))

    def process_spider_output_negative(self):
        return list(self.mw_negative.process_spider_output(self.response, self.reqs, self.spider_negative))

    def test_middleware_works(self):
        self.assertEqual(self.process_spider_output(), [self.short_url_req])
        self.assertEqual(self.process_spider_output_negative(), self.reqs)

    def test_logging(self):
        with LogCapture() as log:
            self.process_spider_output()
            self.process_spider_output_negative()

        ric = self.stats.get_value('urllength/request_ignored_count', spider=self.spider)
        self.assertEqual(ric, 1)
        self.assertIn(f'Ignoring link (url length > {self.maxlength})', str(log))
        ric = self.stats_negative.get_value('urllength/request_ignored_count', spider=self.spider_negative)
        self.assertIsNone(ric)
