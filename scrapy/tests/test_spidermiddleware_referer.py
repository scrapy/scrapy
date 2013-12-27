from unittest import TestCase

from scrapy.http import Response, Request
from scrapy.spider import Spider
from scrapy.contrib.spidermiddleware.referer import RefererMiddleware


class TestRefererMiddleware(TestCase):

    def setUp(self):
        self.spider = Spider('foo')
        self.mw = RefererMiddleware()

    def test_process_spider_output(self):
        res = Response('http://scrapytest.org')
        reqs = [Request('http://scrapytest.org/')]

        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEquals(out[0].headers.get('Referer'),
                          'http://scrapytest.org')

