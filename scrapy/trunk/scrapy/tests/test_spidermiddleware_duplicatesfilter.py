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

        response = Response('http://scrapytest.org/')
        response.request = Request('http://scrapytest.org/')

        r0 = Request('http://scrapytest.org/')
        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')

        filtered = list(mw.process_spider_output(response, [r0, r1, r2, r3], self.spider))

        assert r0 not in filtered
        assert r1 in filtered
        assert r2 in filtered
        assert r3 not in filtered

        mw.filter.close('scrapytest.org')


class SimplePerDomainFilterTest(unittest.TestCase):

    def test_filter(self):
        domain = 'scrapytest.org'
        filter = SimplePerDomainFilter()
        filter.open(domain)
        assert domain in filter

        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')

        assert filter.add(domain, r1)
        assert filter.add(domain, r2)
        assert not filter.add(domain, r3)

        filter.close(domain)
        assert domain not in filter

