import re
from unittest import TestCase

from six.moves.urllib.parse import urlparse

from scrapy.http import Response, Request
from scrapy.spiders import Spider
from scrapy.spidermiddlewares.offsite import OffsiteMiddleware
from scrapy.spidermiddlewares.offsite import URLWarning
from scrapy.utils.test import get_crawler
import warnings


class OffsiteMiddlewareTestCase:
    spider_kwargs = None
    onsite_reqs = []
    offsite_reqs = []

    def setUp(self):
        crawler = get_crawler(Spider)
        self.spider = crawler._create_spider(**self.spider_kwargs)
        self.mw = OffsiteMiddleware.from_crawler(crawler)
        self.mw.spider_opened(self.spider)

    def test_process_spider_output(self):
        """
        Test that the processed spider's output only matches the onsite_reqs.
        """
        resp = Response('http://scrapytest.org')
        reqs = self.onsite_reqs + self.offsite_reqs

        out = list(self.mw.process_spider_output(resp, reqs, self.spider))
        self.assertEqual(out, self.onsite_reqs)


class TestOffsiteMiddleware(OffsiteMiddlewareTestCase, TestCase):
    spider_kwargs = dict(
        name='foo',
        allowed_domains=['scrapytest.org', 'scrapy.org', 'scrapy.test.org'],
    )

    onsite_reqs = [
        Request('http://scrapytest.org/1'),
        Request('http://scrapy.org/1'),
        Request('http://sub.scrapy.org/1'),
        Request('http://offsite.tld/letmepass', dont_filter=True),
        Request('http://scrapy.test.org/'),
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


class TestEmptyDomains(OffsiteMiddlewareTestCase, TestCase):
    spider_kwargs = dict(name='foo', allowed_domains=None)

    onsite_reqs = [
        Request('http://a.com/b.html'),
        Request('http://b.com/1'),
    ]
    offsite_reqs = []


class TestNoAllowedDomainsArgument(TestEmptyDomains):
    spider_kwargs = dict(name='foo')


class TestBadHostnames(OffsiteMiddlewareTestCase, TestCase):
    bad_hostname = urlparse('http:////scrapytest.org').hostname
    spider_kwargs = dict(
        name='foo',
        allowed_domains=['scrapytest.org', None, bad_hostname],
    )

    onsite_reqs = [Request('http://scrapytest.org/1')]
    offsite_reqs = []


class TestURLWarnings(OffsiteMiddlewareTestCase, TestCase):
    spider_kwargs = dict(
        name='foo',
        allowed_domains=['http://scrapytest.org', 'scrapy.org'],
    )

    onsite_reqs = [Request('http://scrapy.org/1')]
    offsite_reqs = [Request('http://scrapytest.org/1')]

    def test_get_host_regex(self):
        self.spider.allowed_domains = ['http://scrapytest.org', 'scrapy.org', 'scrapy.test.org']
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            host_regex = self.mw.get_host_regex(self.spider)
            assert issubclass(w[-1].category, URLWarning)

        self.assertNotIn(re.escape('http://scrapytest.org'), host_regex.pattern)
