from unittest import TestCase
from urllib.parse import urlparse
import warnings

from scrapy.http import Response, Request
from scrapy.spiders import Spider
from scrapy.spidermiddlewares.offsite import OffsiteMiddleware, URLWarning, PortWarning
from scrapy.utils.test import get_crawler


class TestOffsiteMiddleware(TestCase):

    def setUp(self):
        crawler = get_crawler(Spider)
        self.spider = crawler._create_spider(**self._get_spiderargs())
        self.mw = OffsiteMiddleware.from_crawler(crawler)
        self.mw.spider_opened(self.spider)

    def _get_spiderargs(self):
        return dict(name='foo', allowed_domains=['scrapytest.org', 'scrapy.org', 'scrapy.test.org'])

    def test_process_spider_output(self):
        res = Response('http://scrapytest.org')

        onsite_reqs = [
            Request('http://scrapytest.org/1'),
            Request('http://scrapy.org/1'),
            Request('http://sub.scrapy.org/1'),
            Request('http://offsite.tld/letmepass', dont_filter=True),
            Request('http://scrapy.test.org/'),
            Request('http://scrapy.test.org:8000/'),
        ]
        offsite_reqs = [
            Request('http://scrapy2.org'),
            Request('http://offsite.tld/'),
            Request('http://offsite.tld/scrapytest.org'),
            Request('http://offsite.tld/rogue.scrapytest.org'),
            Request('http://rogue.scrapytest.org.haha.com'),
            Request('http://roguescrapytest.org'),
            Request('http://test.org/'),
            Request('http://notscrapy.test.org/'),
        ]
        reqs = onsite_reqs + offsite_reqs

        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEqual(out, onsite_reqs)


class TestOffsiteMiddleware2(TestOffsiteMiddleware):

    def _get_spiderargs(self):
        return dict(name='foo', allowed_domains=None)

    def test_process_spider_output(self):
        res = Response('http://scrapytest.org')
        reqs = [Request('http://a.com/b.html'), Request('http://b.com/1')]
        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEqual(out, reqs)


class TestOffsiteMiddleware3(TestOffsiteMiddleware2):

    def _get_spiderargs(self):
        return dict(name='foo')


class TestOffsiteMiddleware4(TestOffsiteMiddleware3):

    def _get_spiderargs(self):
        bad_hostname = urlparse('http:////scrapytest.org').hostname
        return dict(name='foo', allowed_domains=['scrapytest.org', None, bad_hostname])

    def test_process_spider_output(self):
        res = Response('http://scrapytest.org')
        reqs = [Request('http://scrapytest.org/1')]
        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEqual(out, reqs)


class TestOffsiteMiddleware5(TestOffsiteMiddleware4):

    def test_get_host_regex(self):
        self.spider.allowed_domains = ['http://scrapytest.org', 'scrapy.org', 'scrapy.test.org']
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self.mw.get_host_regex(self.spider)
            assert issubclass(w[-1].category, URLWarning)


class TestOffsiteMiddleware6(TestOffsiteMiddleware4):

    def test_get_host_regex(self):
        self.spider.allowed_domains = ['scrapytest.org:8000', 'scrapy.org', 'scrapy.test.org']
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self.mw.get_host_regex(self.spider)
            assert issubclass(w[-1].category, PortWarning)
