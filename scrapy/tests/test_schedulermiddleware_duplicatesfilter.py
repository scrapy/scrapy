import unittest

from scrapy.http import Request
from scrapy.core.exceptions import IgnoreRequest
from scrapy.contrib.schedulermiddleware.duplicatesfilter import DuplicatesFilterMiddleware


DOMAIN = 'scrapytest.org'

class DuplicatesFilterMiddlewareTest(unittest.TestCase):

    def setUp(self):
        self.mw = DuplicatesFilterMiddleware()
        self.mw.open_domain(DOMAIN)

    def tearDown(self):
        self.mw.close_domain(DOMAIN)

    def test_process_spider_output(self):

        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')
        r4 = Request('http://scrapytest.org/1')

        assert not self.mw.enqueue_request(DOMAIN, r1)
        assert not self.mw.enqueue_request(DOMAIN, r2)
        self.assertRaises(IgnoreRequest, self.mw.enqueue_request, DOMAIN, r3)
        self.assertRaises(IgnoreRequest, self.mw.enqueue_request, DOMAIN, r4)
