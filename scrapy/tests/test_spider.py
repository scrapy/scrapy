from __future__ import with_statement

import gzip, warnings
from cStringIO import StringIO

from twisted.trial import unittest

from scrapy.spider import BaseSpider
from scrapy.http import Response, TextResponse, XmlResponse, HtmlResponse
from scrapy.contrib.spiders.init import InitSpider
from scrapy.contrib.spiders import CrawlSpider, XMLFeedSpider, CSVFeedSpider, SitemapSpider


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

class SitemapSpiderTest(BaseSpiderTest):

    spider_class = SitemapSpider

    BODY = "SITEMAP"
    f = StringIO()
    g = gzip.GzipFile(fileobj=f, mode='w+b')
    g.write(BODY)
    g.close()
    GZBODY = f.getvalue()

    def test_get_sitemap_body(self):
        spider = self.spider_class("example.com")

        r = XmlResponse(url="http://www.example.com/", body=self.BODY)
        self.assertEqual(spider._get_sitemap_body(r), self.BODY)

        r = HtmlResponse(url="http://www.example.com/", body=self.BODY)
        self.assertEqual(spider._get_sitemap_body(r), None)

        r = Response(url="http://www.example.com/favicon.ico", body=self.BODY)
        self.assertEqual(spider._get_sitemap_body(r), None)

        r = Response(url="http://www.example.com/sitemap", body=self.GZBODY, headers={"content-type": "application/gzip"})
        self.assertEqual(spider._get_sitemap_body(r), self.BODY)

        r = TextResponse(url="http://www.example.com/sitemap.xml", body=self.BODY)
        self.assertEqual(spider._get_sitemap_body(r), self.BODY)

        r = Response(url="http://www.example.com/sitemap.xml.gz", body=self.GZBODY)
        self.assertEqual(spider._get_sitemap_body(r), self.BODY)

if __name__ == '__main__':
    unittest.main()
