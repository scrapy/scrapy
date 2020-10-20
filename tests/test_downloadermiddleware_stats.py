from unittest import TestCase

from scrapy.downloadermiddlewares.stats import DownloaderStats
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


class MyException(Exception):
    pass


class TestDownloaderStats(TestCase):

    def setUp(self):
        self.crawler = get_crawler(Spider)
        self.spider = self.crawler._create_spider('scrapytest.org')
        self.mw = DownloaderStats(self.crawler.stats)

        self.crawler.stats.open_spider(self.spider)

        self.req = Request('http://scrapytest.org')
        self.res = Response('scrapytest.org', status=400)

    def assertStatsEqual(self, key, value):
        self.assertEqual(
            self.crawler.stats.get_value(key, spider=self.spider),
            value,
            str(self.crawler.stats.get_stats(self.spider))
        )

    def test_process_request(self):
        self.mw.process_request(self.req, self.spider)
        self.assertStatsEqual('downloader/request_count', 1)

    def test_process_response(self):
        self.mw.process_response(self.req, self.res, self.spider)
        self.assertStatsEqual('downloader/response_count', 1)

    def test_process_exception(self):
        self.mw.process_exception(self.req, MyException(), self.spider)
        self.assertStatsEqual('downloader/exception_count', 1)
        self.assertStatsEqual(
            'downloader/exception_type_count/tests.test_downloadermiddleware_stats.MyException',
            1
        )

    def tearDown(self):
        self.crawler.stats.close_spider(self.spider, '')
