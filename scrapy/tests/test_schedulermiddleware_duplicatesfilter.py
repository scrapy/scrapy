import unittest

from scrapy.http import Request
from scrapy.spider import BaseSpider
from scrapy.core.exceptions import IgnoreRequest
from scrapy.contrib.schedulermiddleware.duplicatesfilter import DuplicatesFilterMiddleware


class DuplicatesFilterMiddlewareTest(unittest.TestCase):

    def setUp(self):
        self.mw = DuplicatesFilterMiddleware()
        self.spider = BaseSpider('foo')
        self.mw.open_spider(self.spider)

    def tearDown(self):
        self.mw.close_spider(self.spider)

    def test_process_spider_output(self):

        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')
        r4 = Request('http://scrapytest.org/1')

        assert not self.mw.enqueue_request(self.spider, r1)
        assert not self.mw.enqueue_request(self.spider, r2)
        self.assertRaises(IgnoreRequest, self.mw.enqueue_request, self.spider, r3)
        self.assertRaises(IgnoreRequest, self.mw.enqueue_request, self.spider, r4)
