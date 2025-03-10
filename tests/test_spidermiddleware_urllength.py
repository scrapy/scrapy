from testfixtures import LogCapture

from scrapy.http import Request, Response
from scrapy.spidermiddlewares.urllength import UrlLengthMiddleware
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


class TestUrlLengthMiddleware:
    def setup_method(self):
        self.maxlength = 25
        crawler = get_crawler(Spider, {"URLLENGTH_LIMIT": self.maxlength})
        self.spider = crawler._create_spider("foo")
        self.stats = crawler.stats
        self.mw = UrlLengthMiddleware.from_crawler(crawler)

        self.response = Response("http://scrapytest.org")
        self.short_url_req = Request("http://scrapytest.org/")
        self.long_url_req = Request("http://scrapytest.org/this_is_a_long_url")
        self.reqs = [self.short_url_req, self.long_url_req]

    def process_spider_output(self):
        return list(
            self.mw.process_spider_output(self.response, self.reqs, self.spider)
        )

    def test_middleware_works(self):
        assert self.process_spider_output() == [self.short_url_req]

    def test_logging(self):
        with LogCapture() as log:
            self.process_spider_output()

        ric = self.stats.get_value(
            "urllength/request_ignored_count", spider=self.spider
        )
        assert ric == 1

        assert f"Ignoring link (url length > {self.maxlength})" in str(log)
