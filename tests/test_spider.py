import gzip
import inspect
import warnings
from io import BytesIO

from testfixtures import LogCapture
from twisted.trial import unittest

from scrapy import signals
from scrapy.settings import Settings
from scrapy.http import Request, Response, TextResponse, XmlResponse, HtmlResponse
from scrapy.spiders.init import InitSpider
from scrapy.spiders import Spider, BaseSpider, CrawlSpider, Rule, XMLFeedSpider, \
    CSVFeedSpider, SitemapSpider
from scrapy.linkextractors import LinkExtractor
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.trackref import object_ref
from scrapy.utils.test import get_crawler

from tests import mock


class SpiderTest(unittest.TestCase):

    spider_class = Spider

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

    def test_deprecated_set_crawler_method(self):
        spider = self.spider_class('example.com')
        crawler = get_crawler()
        with warnings.catch_warnings(record=True) as w:
            spider.set_crawler(crawler)
            self.assertIn("set_crawler", str(w[0].message))
            self.assertTrue(hasattr(spider, 'crawler'))
            self.assertIs(spider.crawler, crawler)
            self.assertTrue(hasattr(spider, 'settings'))
            self.assertIs(spider.settings, crawler.settings)

    def test_from_crawler_crawler_and_settings_population(self):
        crawler = get_crawler()
        spider = self.spider_class.from_crawler(crawler, 'example.com')
        self.assertTrue(hasattr(spider, 'crawler'))
        self.assertIs(spider.crawler, crawler)
        self.assertTrue(hasattr(spider, 'settings'))
        self.assertIs(spider.settings, crawler.settings)

    def test_from_crawler_init_call(self):
        with mock.patch.object(self.spider_class, '__init__',
                               return_value=None) as mock_init:
            self.spider_class.from_crawler(get_crawler(), 'example.com',
                                           foo='bar')
            mock_init.assert_called_once_with('example.com', foo='bar')

    def test_closed_signal_call(self):
        class TestSpider(self.spider_class):
            closed_called = False

            def closed(self, reason):
                self.closed_called = True

        crawler = get_crawler()
        spider = TestSpider.from_crawler(crawler, 'example.com')
        crawler.signals.send_catch_log(signal=signals.spider_opened,
                                       spider=spider)
        crawler.signals.send_catch_log(signal=signals.spider_closed,
                                       spider=spider, reason=None)
        self.assertTrue(spider.closed_called)

    def test_update_settings(self):
        spider_settings = {'TEST1': 'spider', 'TEST2': 'spider'}
        project_settings = {'TEST1': 'project', 'TEST3': 'project'}
        self.spider_class.custom_settings = spider_settings
        settings = Settings(project_settings, priority='project')

        self.spider_class.update_settings(settings)
        self.assertEqual(settings.get('TEST1'), 'spider')
        self.assertEqual(settings.get('TEST2'), 'spider')
        self.assertEqual(settings.get('TEST3'), 'project')

    def test_logger(self):
        spider = self.spider_class('example.com')
        with LogCapture() as l:
            spider.logger.info('test log msg')
        l.check(('example.com', 'INFO', 'test log msg'))

        record = l.records[0]
        self.assertIn('spider', record.__dict__)
        self.assertIs(record.spider, spider)

    def test_log(self):
        spider = self.spider_class('example.com')
        with mock.patch('scrapy.spiders.Spider.logger') as mock_logger:
            spider.log('test log msg', 'INFO')
        mock_logger.log.assert_called_once_with('INFO', 'test log msg')


class InitSpiderTest(SpiderTest):

    spider_class = InitSpider


class XMLFeedSpiderTest(SpiderTest):

    spider_class = XMLFeedSpider

    def test_register_namespace(self):
        body = b"""<?xml version="1.0" encoding="UTF-8"?>
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
                    'loc': selector.xpath('a:loc/text()').extract(),
                    'updated': selector.xpath('b:updated/text()').extract(),
                    'other': selector.xpath('other/@value').extract(),
                    'custom': selector.xpath('other/@b:custom').extract(),
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


class CSVFeedSpiderTest(SpiderTest):

    spider_class = CSVFeedSpider


class CrawlSpiderTest(SpiderTest):

    test_body = b"""<html><head><title>Page title<title>
    <body>
    <p><a href="item/12.html">Item 12</a></p>
    <div class='links'>
    <p><a href="/about.html">About us</a></p>
    </div>
    <div>
    <p><a href="/nofollow.html">This shouldn't be followed</a></p>
    </div>
    </body></html>"""
    spider_class = CrawlSpider

    def test_process_links(self):

        response = HtmlResponse("http://example.org/somepage/index.html",
            body=self.test_body)

        class _CrawlSpider(self.spider_class):
            name="test"
            allowed_domains=['example.org']
            rules = (
                Rule(LinkExtractor(), process_links="dummy_process_links"),
            )

            def dummy_process_links(self, links):
                return links

        spider = _CrawlSpider()
        output = list(spider._requests_to_follow(response))
        self.assertEqual(len(output), 3)
        self.assertTrue(all(map(lambda r: isinstance(r, Request), output)))
        self.assertEquals([r.url for r in output],
                          ['http://example.org/somepage/item/12.html',
                           'http://example.org/about.html',
                           'http://example.org/nofollow.html'])

    def test_process_links_filter(self):

        response = HtmlResponse("http://example.org/somepage/index.html",
            body=self.test_body)

        class _CrawlSpider(self.spider_class):
            import re

            name="test"
            allowed_domains=['example.org']
            rules = (
                Rule(LinkExtractor(), process_links="filter_process_links"),
            )
            _test_regex = re.compile('nofollow')
            def filter_process_links(self, links):
                return [link for link in links
                        if not self._test_regex.search(link.url)]

        spider = _CrawlSpider()
        output = list(spider._requests_to_follow(response))
        self.assertEqual(len(output), 2)
        self.assertTrue(all(map(lambda r: isinstance(r, Request), output)))
        self.assertEquals([r.url for r in output],
                          ['http://example.org/somepage/item/12.html',
                           'http://example.org/about.html'])

    def test_process_links_generator(self):

        response = HtmlResponse("http://example.org/somepage/index.html",
            body=self.test_body)

        class _CrawlSpider(self.spider_class):
            name="test"
            allowed_domains=['example.org']
            rules = (
                Rule(LinkExtractor(), process_links="dummy_process_links"),
            )

            def dummy_process_links(self, links):
                for link in links:
                    yield link

        spider = _CrawlSpider()
        output = list(spider._requests_to_follow(response))
        self.assertEqual(len(output), 3)
        self.assertTrue(all(map(lambda r: isinstance(r, Request), output)))
        self.assertEquals([r.url for r in output],
                          ['http://example.org/somepage/item/12.html',
                           'http://example.org/about.html',
                           'http://example.org/nofollow.html'])

    def test_follow_links_attribute_population(self):
        crawler = get_crawler()
        spider = self.spider_class.from_crawler(crawler, 'example.com')
        self.assertTrue(hasattr(spider, '_follow_links'))
        self.assertTrue(spider._follow_links)

        settings_dict = {'CRAWLSPIDER_FOLLOW_LINKS': False}
        crawler = get_crawler(settings_dict=settings_dict)
        spider = self.spider_class.from_crawler(crawler, 'example.com')
        self.assertTrue(hasattr(spider, '_follow_links'))
        self.assertFalse(spider._follow_links)

    def test_follow_links_attribute_deprecated_population(self):
        spider = self.spider_class('example.com')
        self.assertFalse(hasattr(spider, '_follow_links'))

        spider.set_crawler(get_crawler())
        self.assertTrue(hasattr(spider, '_follow_links'))
        self.assertTrue(spider._follow_links)

        spider = self.spider_class('example.com')
        settings_dict = {'CRAWLSPIDER_FOLLOW_LINKS': False}
        spider.set_crawler(get_crawler(settings_dict=settings_dict))
        self.assertTrue(hasattr(spider, '_follow_links'))
        self.assertFalse(spider._follow_links)


class SitemapSpiderTest(SpiderTest):

    spider_class = SitemapSpider

    BODY = b"SITEMAP"
    f = BytesIO()
    g = gzip.GzipFile(fileobj=f, mode='w+b')
    g.write(BODY)
    g.close()
    GZBODY = f.getvalue()

    def assertSitemapBody(self, response, body):
        spider = self.spider_class("example.com")
        self.assertEqual(spider._get_sitemap_body(response), body)

    def test_get_sitemap_body(self):
        r = XmlResponse(url="http://www.example.com/", body=self.BODY)
        self.assertSitemapBody(r, self.BODY)

        r = HtmlResponse(url="http://www.example.com/", body=self.BODY)
        self.assertSitemapBody(r, None)

        r = Response(url="http://www.example.com/favicon.ico", body=self.BODY)
        self.assertSitemapBody(r, None)

    def test_get_sitemap_body_gzip_headers(self):
        r = Response(url="http://www.example.com/sitemap", body=self.GZBODY,
                     headers={"content-type": "application/gzip"})
        self.assertSitemapBody(r, self.BODY)

    def test_get_sitemap_body_xml_url(self):
        r = TextResponse(url="http://www.example.com/sitemap.xml", body=self.BODY)
        self.assertSitemapBody(r, self.BODY)

    def test_get_sitemap_body_xml_url_compressed(self):
        r = Response(url="http://www.example.com/sitemap.xml.gz", body=self.GZBODY)
        self.assertSitemapBody(r, self.BODY)

    def test_get_sitemap_urls_from_robotstxt(self):
        robots = b"""# Sitemap files
Sitemap: http://example.com/sitemap.xml
Sitemap: http://example.com/sitemap-product-index.xml
Sitemap: HTTP://example.com/sitemap-uppercase.xml
Sitemap: /sitemap-relative-url.xml
"""

        r = TextResponse(url="http://www.example.com/robots.txt", body=robots)
        spider = self.spider_class("example.com")
        self.assertEqual([req.url for req in spider._parse_sitemap(r)],
                         ['http://example.com/sitemap.xml',
                          'http://example.com/sitemap-product-index.xml',
                          'http://example.com/sitemap-uppercase.xml',
                          'http://www.example.com/sitemap-relative-url.xml'])


class DeprecationTest(unittest.TestCase):

    def test_basespider_is_deprecated(self):
        with warnings.catch_warnings(record=True) as w:

            class MySpider1(BaseSpider):
                pass

            self.assertEqual(len(w), 1)
            self.assertEqual(w[0].category, ScrapyDeprecationWarning)
            self.assertEqual(w[0].lineno, inspect.getsourcelines(MySpider1)[1])

    def test_basespider_issubclass(self):
        class MySpider2(Spider):
            pass

        class MySpider2a(MySpider2):
            pass

        class Foo(object):
            pass

        class Foo2(object_ref):
            pass

        assert issubclass(MySpider2, BaseSpider)
        assert issubclass(MySpider2a, BaseSpider)
        assert not issubclass(Foo, BaseSpider)
        assert not issubclass(Foo2, BaseSpider)

    def test_basespider_isinstance(self):
        class MySpider3(Spider):
            name = 'myspider3'

        class MySpider3a(MySpider3):
            pass

        class Foo(object):
            pass

        class Foo2(object_ref):
            pass

        assert isinstance(MySpider3(), BaseSpider)
        assert isinstance(MySpider3a(), BaseSpider)
        assert not isinstance(Foo(), BaseSpider)
        assert not isinstance(Foo2(), BaseSpider)

    def test_crawl_spider(self):
        assert issubclass(CrawlSpider, Spider)
        assert issubclass(CrawlSpider, BaseSpider)
        assert isinstance(CrawlSpider(name='foo'), Spider)
        assert isinstance(CrawlSpider(name='foo'), BaseSpider)

    def test_make_requests_from_url_deprecated(self):
        class MySpider4(Spider):
            name = 'spider1'
            start_urls = ['http://example.com']

        class MySpider5(Spider):
            name = 'spider2'
            start_urls = ['http://example.com']

            def make_requests_from_url(self, url):
                return Request(url + "/foo", dont_filter=True)

        with warnings.catch_warnings(record=True) as w:
            # spider without overridden make_requests_from_url method
            # doesn't issue a warning
            spider1 = MySpider4()
            self.assertEqual(len(list(spider1.start_requests())), 1)
            self.assertEqual(len(w), 0)

            # spider with overridden make_requests_from_url issues a warning,
            # but the method still works
            spider2 = MySpider5()
            requests = list(spider2.start_requests())
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].url, 'http://example.com/foo')
            self.assertEqual(len(w), 1)
