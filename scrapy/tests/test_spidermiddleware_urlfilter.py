from unittest import TestCase

from scrapy.contrib.spidermiddleware.urlfilter import UrlFilterMiddleware
from scrapy.http import Response, Request
from scrapy.spider import BaseSpider
from scrapy.utils.url import canonicalize_url


class TestUrlFilterMiddleware(TestCase):

    def setUp(self):
        self.spider = BaseSpider('foo')
        self.mw = UrlFilterMiddleware()

    def test_process_spider_output(self):
        res = Response('http://scrapytest.org')
        req_url = 'http://scrapytest.org/?last=1&first=2'
        reqs = [Request(req_url)]

        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEquals(out[0].url, canonicalize_url(req_url))

