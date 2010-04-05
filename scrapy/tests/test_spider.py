from __future__ import with_statement

import sys
import warnings

from twisted.trial import unittest

from scrapy.spider import BaseSpider
from scrapy.contrib.spiders.init import InitSpider
from scrapy.contrib.spiders.crawl import CrawlSpider
from scrapy.contrib.spiders.feed import XMLFeedSpider, CSVFeedSpider
from scrapy.contrib.dupefilter import RequestFingerprintDupeFilter, NullDupeFilter


class BaseSpiderTest(unittest.TestCase):

    spider_class = BaseSpider

    class OldSpider(spider_class):

        domain_name = 'example.com'
        extra_domain_names = ('example.org', 'example.net')


    class OldSpiderWithoutExtradomains(spider_class):

        domain_name = 'example.com'


    class NewSpider(spider_class):

        name = 'example.com'
        allowed_domains = ('example.org', 'example.net')


    def setUp(self):
        warnings.simplefilter("always")

    def tearDown(self):
        warnings.resetwarnings()

    def test_sep12_deprecation_warnings(self):
        if sys.version_info[:2] < (2, 6):
            # warnings.catch_warnings() was added in Python 2.6
            raise unittest.SkipTest("This test requires Python 2.6+")
        with warnings.catch_warnings(record=True) as w:
            spider = self.OldSpider()
            self.assertEqual(len(w), 2) # one for domain_name & one for extra_domain_names
            self.assert_(issubclass(w[-1].category, DeprecationWarning))

    def test_sep12_backwards_compatibility(self):
        spider = self.OldSpider()
        self.assertEqual(spider.name, 'example.com')
        self.assert_('example.com' in spider.allowed_domains, spider.allowed_domains)
        self.assert_('example.org' in spider.allowed_domains, spider.allowed_domains)
        self.assert_('example.net' in spider.allowed_domains, spider.allowed_domains)

        spider = self.OldSpiderWithoutExtradomains()
        self.assertEqual(spider.name, 'example.com')
        self.assert_('example.com' in spider.allowed_domains, spider.allowed_domains)

        spider = self.NewSpider()
        self.assertEqual(spider.domain_name, 'example.com')
        self.assert_('example.org' in spider.extra_domain_names, spider.extra_domain_names)
        self.assert_('example.net' in spider.extra_domain_names, spider.extra_domain_names)

    def test_base_spider(self):
        spider = self.spider_class("example.com")
        self.assertEqual(spider.name, 'example.com')
        self.assertEqual(spider.start_urls, [])
        self.assertEqual(spider.allowed_domains, [])

    def test_spider_args(self):
        """Constructor arguments are assigned to spider attributes"""
        spider = self.spider_class('example.com', foo='bar')
        self.assertEqual(spider.foo, 'bar')

    def test_spider_without_name(self):
        """Constructor arguments are assigned to spider attributes"""
        spider = self.spider_class()
        self.assertEqual(spider.name, 'default')
        spider = self.spider_class(foo='bar')
        self.assertEqual(spider.foo, 'bar')


class InitSpiderTest(BaseSpiderTest):

    spider_class = InitSpider

class XMLFeedSpiderTest(BaseSpiderTest):

    spider_class = XMLFeedSpider

class CSVFeedSpiderTest(BaseSpiderTest):

    spider_class = CSVFeedSpider

class CrawlSpiderTest(BaseSpiderTest):

    spider_class = CrawlSpider


if __name__ == '__main__':
    unittest.main()
