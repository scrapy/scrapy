from unittest import TestCase

from six.moves.urllib.parse import urlparse

from scrapy.http import Response, Request
from scrapy.spider import Spider
from scrapy.contrib.spidermiddleware.offsite import OffsiteMiddleware
from scrapy.utils.test import get_crawler


class TestOffsiteMiddleware(TestCase):

    def setUp(self):
        self.spider = self._get_spider()
        crawler = get_crawler()
        self.mw = OffsiteMiddleware.from_crawler(crawler)
        self.mw.spider_opened(self.spider)

    def _get_spider(self):
        return Spider('foo', allowed_domains=['scrapytest.org', 'scrapy.org'])

    def test_process_spider_output(self):
        res = Response(b'http://scrapytest.org')
        onsite_reqs = [
            Request(b'http://scrapytest.org/1'),
            Request(b'http://scrapy.org/1'),
            Request(b'http://sub.scrapy.org/1'),
            Request(b'http://offsite.tld/letmepass', dont_filter=True),
        ]
        offsite_reqs = [
            Request(b'http://scrapy2.org'),
            Request(b'http://offsite.tld/'),
            Request(b'http://offsite.tld/scrapytest.org'),
            Request(b'http://offsite.tld/rogue.scrapytest.org'),
            Request(b'http://rogue.scrapytest.org.haha.com'),
            Request(b'http://roguescrapytest.org'),
        ]
        reqs = onsite_reqs + offsite_reqs
        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEquals(out, onsite_reqs)


class TestOffsiteMiddleware2(TestOffsiteMiddleware):

    def _get_spider(self):
        return Spider('foo', allowed_domains=None)

    def test_process_spider_output(self):
        res = Response(b'http://scrapytest.org')
        reqs = [Request(b'http://a.com/b.html'), Request(b'http://b.com/1')]
        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEquals(out, reqs)


class TestOffsiteMiddleware3(TestOffsiteMiddleware2):

    def _get_spider(self):
        return Spider('foo')


class TestOffsiteMiddleware4(TestOffsiteMiddleware3):

    def _get_spider(self):
        bad_hostname = urlparse('http:////scrapytest.org').hostname
        return Spider('foo', allowed_domains=['scrapytest.org', None, bad_hostname])

    def test_process_spider_output(self):
        res = Response(b'http://scrapytest.org')
        reqs = [Request(b'http://scrapytest.org/1')]
        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEquals(out, reqs)
