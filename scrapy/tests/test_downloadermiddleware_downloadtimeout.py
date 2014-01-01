import unittest

from scrapy.contrib.downloadermiddleware.downloadtimeout import DownloadTimeoutMiddleware
from scrapy.spider import Spider
from scrapy.http import Request
from scrapy.utils.test import get_crawler


class DownloadTimeoutMiddlewareTest(unittest.TestCase):

    def get_request_spider_mw(self):
        crawler = get_crawler()
        spider = Spider('foo')
        spider.set_crawler(crawler)
        request = Request('http://scrapytest.org/')
        return request, spider, DownloadTimeoutMiddleware.from_crawler(crawler)

    def test_default_download_timeout(self):
        req, spider, mw = self.get_request_spider_mw()
        mw.spider_opened(spider)
        assert mw.process_request(req, spider) is None
        self.assertEquals(req.meta.get('download_timeout'), 180)

    def test_spider_has_download_timeout(self):
        req, spider, mw = self.get_request_spider_mw()
        spider.download_timeout = 2
        mw.spider_opened(spider)
        assert mw.process_request(req, spider) is None
        self.assertEquals(req.meta.get('download_timeout'), 2)

    def test_request_has_download_timeout(self):
        req, spider, mw = self.get_request_spider_mw()
        spider.download_timeout = 2
        mw.spider_opened(spider)
        req.meta['download_timeout'] = 1
        assert mw.process_request(req, spider) is None
        self.assertEquals(req.meta.get('download_timeout'), 1)
