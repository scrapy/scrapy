from unittest import TestCase

from scrapy.http import Response, Request
from scrapy.spider import BaseSpider
from scrapy.contrib.spidermiddleware.offsite import OffsiteMiddleware


class TestOffsiteMiddleware(TestCase):

    def setUp(self):
        self.spider = self._get_spider()
        self.mw = OffsiteMiddleware()
        self.mw.spider_opened(self.spider)

    def _get_spider(self):
        return BaseSpider('foo', allowed_domains=['scrapytest.org', 'scrapy.org'])

    def test_process_spider_output(self):
        res = Response('http://scrapytest.org')

        onsite_reqs = [Request('http://scrapytest.org/1'),
                       Request('http://scrapy.org/1'),
                       Request('http://sub.scrapy.org/1'),
                       Request('http://offsite.tld/letmepass', dont_filter=True)]
        offsite_reqs = [Request('http://scrapy2.org'),
                       Request('http://offsite.tld/')]
        reqs = onsite_reqs + offsite_reqs

        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEquals(out, onsite_reqs)

    def tearDown(self):
        self.mw.spider_closed(self.spider)


class TestOffsiteMiddleware2(TestOffsiteMiddleware):

    def _get_spider(self):
        return BaseSpider('foo', allowed_domains=None)

    def test_process_spider_output(self):
        res = Response('http://scrapytest.org')
        reqs = [Request('http://a.com/b.html'), Request('http://b.com/1')]
        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEquals(out, reqs)

class TestOffsiteMiddleware3(TestOffsiteMiddleware2):

    def _get_spider(self):
        return BaseSpider('foo')

