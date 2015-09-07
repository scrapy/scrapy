from unittest import TestCase

from scrapy.downloadermiddlewares.defaultheaders import DefaultHeadersMiddleware
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from scrapy.utils.python import to_bytes


class TestDefaultHeadersMiddleware(TestCase):

    def get_defaults_spider_mw(self):
        crawler = get_crawler(Spider)
        spider = crawler._create_spider('foo')
        defaults = {
            to_bytes(k): [to_bytes(v)]
            for k, v in crawler.settings.get('DEFAULT_REQUEST_HEADERS').items()
        }
        return defaults, spider, DefaultHeadersMiddleware.from_crawler(crawler)

    def test_process_request(self):
        defaults, spider, mw = self.get_defaults_spider_mw()
        req = Request('http://www.scrapytest.org')
        mw.process_request(req, spider)
        self.assertEquals(req.headers, defaults)

    def test_update_headers(self):
        defaults, spider, mw = self.get_defaults_spider_mw()
        headers = {'Accept-Language': ['es'], 'Test-Header': ['test']}
        bytes_headers = {b'Accept-Language': [b'es'], b'Test-Header': [b'test']}
        req = Request('http://www.scrapytest.org', headers=headers)
        self.assertEquals(req.headers, bytes_headers)

        mw.process_request(req, spider)
        defaults.update(bytes_headers)
        self.assertEquals(req.headers, defaults)
