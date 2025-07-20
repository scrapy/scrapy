from twisted.trial import unittest as trial_unittest

from scrapy import Request, Spider
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging


class LowercaseHeaderTests(trial_unittest.TestCase):
    def setUp(self):
        configure_logging({"LOG_LEVEL": "ERROR"})

    def test_lowercase_headers_preserved(self):
        class TestSpider(Spider):
            name = "lowercase_spider"

            def start_requests(self):
                yield Request(
                    url="https://httpbin.org/headers",
                    headers={"x-my-lower-header": "test-value"},
                    callback=self.parse,
                    meta={"KEEP_LOWERCASE_HEADERS": True},
                )

            def parse(self, response):
                headers = response.request.headers
                assert b"x-my-lower-header" in headers
                assert headers[b"x-my-lower-header"] == [b"test-value"]
                assert b"X-My-Lower-Header" not in headers

        runner = CrawlerRunner()
        return runner.crawl(TestSpider)

    def test_default_header_casing(self):
        class TestSpider(Spider):
            name = "default_header_spider"

            def start_requests(self):
                yield Request(
                    url="https://httpbin.org/headers",
                    headers={"x-my-lower-header": "test-value"},
                    callback=self.parse,
                )

            def parse(self, response):
                headers = response.request.headers
                assert b"X-My-Lower-Header" in headers
                assert headers[b"X-My-Lower-Header"] == [b"test-value"]
                assert b"x-my-lower-header" not in headers

        runner = CrawlerRunner()
        return runner.crawl(TestSpider)
