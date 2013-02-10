import gzip
import inspect
import warnings
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

    def test_start_requests(self):
        spider = self.spider_class('example.com')
        start_requests = spider.start_requests()
        self.assertTrue(inspect.isgenerator(start_requests))
        self.assertEqual(list(start_requests), [])

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

    def test_register_namespace(self):
        body = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns:x="http://www.google.com/schemas/sitemap/0.84"
                xmlns:y="http://www.example.com/schemas/extras/1.0">
        <url><x:loc>http://www.example.com/Special-Offers.html</loc><y:updated>2009-08-16</updated><other value="bar" y:custom="fuu"/></url>
        <url><loc>http://www.example.com/</loc><y:updated>2009-08-16</updated><other value="foo"/></url>
        </urlset>"""
        response = XmlResponse(url='http://example.com/sitemap.xml', body=body)

        class _XMLSpider(self.spider_class):
            itertag = 'url'
            namespaces = (
                ('a', 'http://www.google.com/schemas/sitemap/0.84'),
                ('b', 'http://www.example.com/schemas/extras/1.0'),
            )

            def parse_node(self, response, selector):
                yield {
                    'loc': selector.select('a:loc/text()').extract(),
                    'updated': selector.select('b:updated/text()').extract(),
                    'other': selector.select('other/@value').extract(),
                    'custom': selector.select('other/@b:custom').extract(),
                }

        for iterator in ('iternodes', 'xml'):
            spider = _XMLSpider('example', iterator=iterator)
            output = list(spider.parse(response))
            self.assertEqual(len(output), 2, iterator)
            self.assertEqual(output, [
                {'loc': [u'http://www.example.com/Special-Offers.html'],
                 'updated': [u'2009-08-16'],
                 'custom': [u'fuu'],
                 'other': [u'bar']},
                {'loc': [],
                 'updated': [u'2009-08-16'],
                 'other': [u'foo'],
                 'custom': []},
            ], iterator)


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
