from unittest import TestCase

from scrapy.conf import settings
from scrapy.contrib.downloadermiddleware.defaultheaders import DefaultHeadersMiddleware
from scrapy.http import Request
from scrapy.spider import BaseSpider


class TestDefaultHeadersMiddleware(TestCase):

    def setUp(self):
        self.spider = BaseSpider('foo')
        self.mw = DefaultHeadersMiddleware()
        self.default_request_headers = dict([(k, [v]) for k, v in \
            settings.get('DEFAULT_REQUEST_HEADERS').iteritems()])

    def test_process_request(self):
        req = Request('http://www.scrapytest.org')
        self.mw.process_request(req, self.spider)
        self.assertEquals(req.headers, self.default_request_headers)

    def test_spider_default_request_headers(self):
        spider_headers = {'Unexistant-Header': ['value']}
        # override one of the global default headers by spider
        if self.default_request_headers:
            k = set(self.default_request_headers).pop()
            spider_headers[k] = ['__newvalue__']
        self.spider.default_request_headers = spider_headers

        req = Request('http://www.scrapytest.org')
        self.mw.process_request(req, self.spider)
        self.assertEquals(req.headers, dict(self.default_request_headers, **spider_headers))

    def test_update_headers(self):
        headers = {'Accept-Language': ['es'], 'Test-Header': ['test']}
        req = Request('http://www.scrapytest.org', headers=headers)
        self.assertEquals(req.headers, headers)

        self.mw.process_request(req, self.spider)
        self.default_request_headers.update(headers)
        self.assertEquals(req.headers, self.default_request_headers)

