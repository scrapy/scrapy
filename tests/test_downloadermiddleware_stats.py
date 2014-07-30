from unittest import TestCase

from scrapy.contrib.downloadermiddleware.stats import DownloaderStats
from scrapy.http import Request, Response
from scrapy.spider import Spider
from scrapy.utils.test import get_crawler


class TestDownloaderStats(TestCase):

    def setUp(self):
        self.crawler = get_crawler()
        self.spider = Spider('scrapytest.org')
        self.mw = DownloaderStats(self.crawler.stats)

        self.crawler.stats.open_spider(self.spider)

        self.req = Request('http://scrapytest.org')
        self.res = Response('scrapytest.org', status=400)

    def test_process_request(self):
        self.mw.process_request(self.req, self.spider)
        self.assertEqual(self.crawler.stats.get_value('downloader/request_count', \
            spider=self.spider), 1)
        
    def test_process_response(self):
        self.mw.process_response(self.req, self.res, self.spider)
        self.assertEqual(self.crawler.stats.get_value('downloader/response_count', \
            spider=self.spider), 1)

    def test_process_exception(self):
        self.mw.process_exception(self.req, Exception(), self.spider)
        self.assertEqual(self.crawler.stats.get_value('downloader/exception_count', \
            spider=self.spider), 1)

    def tearDown(self):
        self.crawler.stats.close_spider(self.spider, '')

