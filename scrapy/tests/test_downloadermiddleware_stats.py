from unittest import TestCase

from scrapy.conf import settings
from scrapy.contrib.downloadermiddleware.stats import DownloaderStats
from scrapy.http import Request, Response
from scrapy.spider import BaseSpider
from scrapy.stats import stats


class TestDownloaderStats(TestCase):

    def setUp(self):
        self.spider = BaseSpider()
        self.spider.domain_name = 'scrapytest.org'
        self.mw = DownloaderStats()

        stats.open_domain(self.spider.domain_name)

        self.req = Request('scrapytest.org')
        self.res = Response('scrapytest.org', status=400)

    def test_process_request(self):
        self.mw.process_request(self.req, self.spider)
        self.assertEqual(stats.get_value('downloader/request_count', \
            domain=self.spider.domain_name), 1)
        
    def test_process_response(self):
        self.mw.process_response(self.req, self.res, self.spider)
        self.assertEqual(stats.get_value('downloader/response_count', \
            domain=self.spider.domain_name), 1)

    def test_process_exception(self):
        self.mw.process_exception(self.req, Exception(), self.spider)
        self.assertEqual(stats.get_value('downloader/exception_count', \
            domain=self.spider.domain_name), 1)

    def tearUp(self):
        stats.close_domain(self.spider.domain_name)

