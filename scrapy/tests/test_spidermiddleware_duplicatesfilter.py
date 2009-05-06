import unittest

from scrapy.spider import spiders
from scrapy.http import Request, Response
from scrapy.core.exceptions import IgnoreRequest
from scrapy.contrib.spidermiddleware.duplicatesfilter import DuplicatesFilterMiddleware
from scrapy.dupefilter import dupefilter

class DuplicatesFilterMiddlewareTest(unittest.TestCase):

    def setUp(self):
        spiders.spider_modules = ['scrapy.tests.test_spiders']
        spiders.reload()
        self.spider = spiders.fromdomain('scrapytest.org')
        dupefilter.open('scrapytest.org')

    def tearDown(self):
        dupefilter.close('scrapytest.org')

    def test_process_spider_output(self):
        mw = DuplicatesFilterMiddleware()

        response = Response('http://scrapytest.org/')
        response.request = Request('http://scrapytest.org/')

        r0 = Request('http://scrapytest.org/')
        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')

        dupefilter.add('scrapytest.org', r0)
        dupefilter.add('scrapytest.org', r2)

        filtered = list(mw.process_spider_output(response, [r0, r1, r2, r3], self.spider))

        assert r0 not in filtered
        assert r1 in filtered
        assert r2 not in filtered
        assert r3 not in filtered
