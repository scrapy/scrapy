import unittest

from scrapy.spider import spiders
from scrapy.http import Request, Response
from scrapy.core.exceptions import IgnoreRequest
from scrapy.contrib.schedulermiddleware.duplicatesfilter import DuplicatesFilterMiddleware
from scrapy.core.filters import duplicatesfilter


class DuplicatesFilterMiddlewareTest(unittest.TestCase):

    def setUp(self):
        duplicatesfilter.open('scrapytest.org')

    def tearDown(self):
        duplicatesfilter.close('scrapytest.org')

    def test_process_spider_output(self):
        domain = 'scrapytest.org'

        mw = DuplicatesFilterMiddleware()

        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')
        r4 = Request('http://scrapytest.org/1')

        assert not mw.enqueue_request(domain, r1, 1)
        assert not mw.enqueue_request(domain, r2, 1)
        self.assertRaises(IgnoreRequest, mw.enqueue_request, domain, r3, 1)
        self.assertRaises(IgnoreRequest, mw.enqueue_request, domain, r4, 1)
