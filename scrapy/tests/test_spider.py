from __future__ import with_statement

import warnings

from twisted.trial import unittest

from scrapy.spider import BaseSpider
from scrapy.contrib.spiders.init import InitSpider
from scrapy.contrib.spiders import CrawlSpider, XMLFeedSpider, CSVFeedSpider


class BaseSpiderTest(unittest.TestCase):

    spider_class = BaseSpider

    def setUp(self):
        warnings.simplefilter("always")

    def tearDown(self):
        warnings.resetwarnings()

    def test_base_spider(self):
        spider = self.spider_class("example.com")
        self.assertEqual(spider.name, 'example.com')
        self.assertEqual(spider.start_urls, [])

    def test_spider_args(self):
        """Constructor arguments are assigned to spider attributes"""
        spider = self.spider_class('example.com', foo='bar')
        self.assertEqual(spider.foo, 'bar')

    def test_spider_without_name(self):
        """Constructor arguments are assigned to spider attributes"""
        self.assertRaises(ValueError, self.spider_class)
        self.assertRaises(ValueError, self.spider_class, somearg='foo')


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
