from unittest import TestCase

from scrapy.conf import settings
from scrapy.contrib.downloadermiddleware.defaultheaders import DefaultHeadersMiddleware
from scrapy.http import Request
from scrapy.spider import BaseSpider
from scrapy.utils.test import get_crawler


class TestDefaultHeadersMiddleware(TestCase):

    def get_defaults_spider_mw(self):
        crawler = get_crawler()
        spider = BaseSpider('foo')
        spider.set_crawler(crawler)
        defaults = dict([(k, [v]) for k, v in \
            crawler.settings.get('DEFAULT_REQUEST_HEADERS').iteritems()])
        return defaults, spider, DefaultHeadersMiddleware()

    def test_process_request(self):
        defaults, spider, mw = self.get_defaults_spider_mw()
        req = Request('http://www.scrapytest.org')
        mw.process_request(req, spider)
        self.assertEquals(req.headers, defaults)

    def test_spider_default_request_headers(self):
        defaults, spider, mw = self.get_defaults_spider_mw()
        spider_headers = {'Unexistant-Header': ['value']}
        # override one of the global default headers by spider
        if defaults:
            k = set(defaults).pop()
            spider_headers[k] = ['__newvalue__']
        spider.DEFAULT_REQUEST_HEADERS = spider_headers

        req = Request('http://www.scrapytest.org')
        mw.process_request(req, spider)
        self.assertEquals(req.headers, dict(spider_headers))

    def test_update_headers(self):
        defaults, spider, mw = self.get_defaults_spider_mw()
        headers = {'Accept-Language': ['es'], 'Test-Header': ['test']}
        req = Request('http://www.scrapytest.org', headers=headers)
        self.assertEquals(req.headers, headers)

        mw.process_request(req, spider)
        defaults.update(headers)
        self.assertEquals(req.headers, defaults)
