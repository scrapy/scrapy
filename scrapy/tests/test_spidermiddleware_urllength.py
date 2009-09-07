from unittest import TestCase

from scrapy.conf import settings
from scrapy.contrib.spidermiddleware.urllength import UrlLengthMiddleware
from scrapy.http import Response, Request
from scrapy.spider import BaseSpider


class TestUrlLengthMiddleware(TestCase):

    def setUp(self):
        settings.disabled = False
        settings.overrides['URLLENGTH_LIMIT'] = 25

        self.spider = BaseSpider()
        self.mw = UrlLengthMiddleware()

    def test_process_spider_output(self):
        res = Response('http://scrapytest.org')

        short_url_req = Request('http://scrapytest.org/')
        long_url_req = Request('http://scrapytest.org/this_is_a_long_url')
        reqs = [short_url_req, long_url_req] 

        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEquals(out, [short_url_req])

    def tearDown(self):
        del settings.overrides['URLLENGTH_LIMIT']
        settings.disabled = True

