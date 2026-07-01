import pytest

from scrapy.downloadermiddlewares.stats import DownloaderStats, get_header_size
from scrapy.exceptions import NotConfigured
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


class MyException(Exception):
    pass


class TestDownloaderStats:
    def setup_method(self):
        self.crawler = get_crawler(Spider)
        self.mw = DownloaderStats(self.crawler.stats)

        self.crawler.stats.open_spider()

        self.req = Request("http://scrapytest.org")
        self.res = Response("http://scrapytest.org", status=400)

    def assertStatsEqual(self, key, value):
        assert self.crawler.stats.get_value(key) == value, str(
            self.crawler.stats.get_stats()
        )

    def test_process_request(self):
        self.mw.process_request(self.req)
        self.assertStatsEqual("downloader/request_count", 1)

    def test_process_response(self):
        self.mw.process_response(self.req, self.res)
        self.assertStatsEqual("downloader/response_count", 1)

    def test_process_exception(self):
        self.mw.process_exception(self.req, MyException())
        self.assertStatsEqual("downloader/exception_count", 1)
        self.assertStatsEqual(
            "downloader/exception_type_count/tests.test_downloadermiddleware_stats.MyException",
            1,
        )

    def test_from_crawler_not_configured(self):
        crawler = get_crawler(Spider, {"DOWNLOADER_STATS": False})
        with pytest.raises(NotConfigured):
            DownloaderStats.from_crawler(crawler)

    def teardown_method(self):
        self.crawler.stats.close_spider()


def test_get_header_size_non_list_value():
    assert get_header_size({"Content-Type": "text/html"}) == 0
