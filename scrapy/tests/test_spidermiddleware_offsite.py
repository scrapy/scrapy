from unittest import TestCase

from scrapy.http import Response, Request
from scrapy.spider import BaseSpider
from scrapy.contrib.spidermiddleware.offsite import OffsiteMiddleware


class TestOffsiteMiddleware(TestCase):

    def setUp(self):
        self.spider = BaseSpider()
        self.spider.name = 'scrapytest.org'
        self.spider.allowed_domains = ['scrapytest.org', 'scrapy.org']

        self.mw = OffsiteMiddleware()
        self.mw.spider_opened(self.spider)

    def test_process_spider_output(self):
        res = Response('http://scrapytest.org')

        onsite_reqs = [Request('http://scrapytest.org/1'),
                       Request('http://scrapy.org/1'),
                       Request('http://sub.scrapy.org/1')]
        offsite_reqs = [Request('http://scrapy2.org')]
        reqs = onsite_reqs + offsite_reqs

        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEquals(out, onsite_reqs)

    def tearDown(self):
        self.mw.spider_closed(self.spider)

