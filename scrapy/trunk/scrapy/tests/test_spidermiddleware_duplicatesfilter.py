import unittest

from scrapy.spider import spiders
from scrapy.http import Request, Response
from scrapy.contrib.spidermiddleware.duplicatesfilter import DuplicatesFilterMiddleware, SimplePerDomainFilter

class DuplicatesFilterMiddlewareTest(unittest.TestCase):

    def setUp(self):
        spiders.spider_modules = ['scrapy.tests.test_spiders']
        spiders.reload()
        self.spider = spiders.fromdomain('scrapytest.org')

    def test_process_spider_output(self):
        mw = DuplicatesFilterMiddleware()
        mw.filter.open('scrapytest.org')

        rq = Request('http://scrapytest.org/')
        response = Response('http://scrapytest.org/')
        response.request = rq
        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')

        filtered = list(mw.process_spider_output(response, [r1, r2, r3], self.spider))

        self.assertFalse(rq in filtered)
        self.assertTrue(r1 in filtered)
        self.assertTrue(r2 in filtered)
        self.assertFalse(r3 in filtered)

        mw.filter.close('scrapytest.org')


class SimplePerDomainFilterTest(unittest.TestCase):

    def test_filter(self):
        domain = 'scrapytest.org'
        filter = SimplePerDomainFilter()
        filter.open(domain)
        self.assertTrue(domain in filter)

        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')

        self.assertTrue(filter.add(domain, r1))
        self.assertTrue(filter.add(domain, r2))
        self.assertFalse(filter.add(domain, r3))

        filter.close(domain)
        self.assertFalse(domain in filter)

