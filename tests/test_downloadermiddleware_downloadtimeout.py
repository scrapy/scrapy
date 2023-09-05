import unittest

from scrapy.downloadermiddlewares.downloadtimeout import DownloadTimeoutMiddleware
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


class DownloadTimeoutMiddlewareTest(unittest.TestCase):
    def get_request_spider_mw(self, settings=None):
        crawler = get_crawler(Spider, settings)
        spider = crawler._create_spider("foo")
        request = Request("http://scrapytest.org/")
        return request, spider, DownloadTimeoutMiddleware.from_crawler(crawler)

    def test_default_download_timeout(self):
        req, spider, mw = self.get_request_spider_mw()
        mw.spider_opened(spider)
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta.get("download_timeout"), 180)

    def test_string_download_timeout(self):
        req, spider, mw = self.get_request_spider_mw({"DOWNLOAD_TIMEOUT": "20.1"})
        mw.spider_opened(spider)
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta.get("download_timeout"), 20.1)

    def test_spider_has_download_timeout(self):
        req, spider, mw = self.get_request_spider_mw()
        spider.download_timeout = 2
        mw.spider_opened(spider)
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta.get("download_timeout"), 2)

    def test_request_has_download_timeout(self):
        req, spider, mw = self.get_request_spider_mw()
        spider.download_timeout = 2
        mw.spider_opened(spider)
        req.meta["download_timeout"] = 1
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.meta.get("download_timeout"), 1)
