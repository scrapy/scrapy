import unittest

from scrapy.contrib.downloadermiddleware.downloadtimeout import DownloadTimeoutMiddleware
from scrapy.spider import BaseSpider
from scrapy.http import Request


class DownloadTimeoutMiddlewareTest(unittest.TestCase):

    def setUp(self):
        self.mw = DownloadTimeoutMiddleware()
        self.spider = BaseSpider('foo')
        self.req = Request('http://scrapytest.org/')

    def tearDown(self):
        del self.mw
        del self.spider
        del self.req

    def test_spider_has_no_download_timeout(self):
        assert self.mw.process_request(self.req, self.spider) is None
        assert 'download_timeout' not in self.req.meta

    def test_spider_has_download_timeout(self):
        self.spider.download_timeout = 2
        assert self.mw.process_request(self.req, self.spider) is None
        self.assertEquals(self.req.meta.get('download_timeout'), 2)

    def test_request_has_download_timeout(self):
        self.spider.download_timeout = 2
        self.req.meta['download_timeout'] = 1
        assert self.mw.process_request(self.req, self.spider) is None
        self.assertEquals(self.req.meta.get('download_timeout'), 1)
