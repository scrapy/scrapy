from unittest import TestCase

from scrapy.conf import settings
from scrapy.contrib.downloadermiddleware.defaultheaders import DefaultHeadersMiddleware
from scrapy.http import Response, Request
from scrapy.spider import BaseSpider


class TestDefaultHeadersMiddleware(TestCase):

    def setUp(self):
        self.spider = BaseSpider('foo')
        self.mw = DefaultHeadersMiddleware()
        self.default_headers = dict([(k, [v]) for k, v in \
            settings.get('DEFAULT_REQUEST_HEADERS').iteritems()])

    def test_process_request(self):
        req = Request('http://www.scrapytest.org')
        self.mw.process_request(req, self.spider)
        self.assertEquals(req.headers, self.default_headers)

    def test_update_headers(self):
        headers = {'Accept-Language': ['es'], 'Test-Header': ['test']}
        req = Request('http://www.scrapytest.org', headers=headers)
        self.assertEquals(req.headers, headers)

        self.mw.process_request(req, self.spider)
        self.default_headers.update(headers)
        self.assertEquals(req.headers, self.default_headers)

