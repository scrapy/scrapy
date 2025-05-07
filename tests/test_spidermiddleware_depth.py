from scrapy.http import Request, Response
from scrapy.spidermiddlewares.depth import DepthMiddleware
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


class TestDepthMiddleware:
    def setup_method(self):
        crawler = get_crawler(Spider, {"DEPTH_LIMIT": 1, "DEPTH_STATS_VERBOSE": True})
        self.spider = crawler._create_spider("scrapytest.org")

        self.stats = crawler.stats
        self.stats.open_spider(self.spider)

        self.mw = DepthMiddleware.from_crawler(crawler)

    def test_process_spider_output(self):
        req = Request("http://scrapytest.org")
        resp = Response("http://scrapytest.org")
        resp.request = req
        result = [Request("http://scrapytest.org")]

        out = list(self.mw.process_spider_output(resp, result, self.spider))
        assert out == result

        rdc = self.stats.get_value("request_depth_count/1", spider=self.spider)
        assert rdc == 1

        req.meta["depth"] = 1

        out2 = list(self.mw.process_spider_output(resp, result, self.spider))
        assert not out2

        rdm = self.stats.get_value("request_depth_max", spider=self.spider)
        assert rdm == 1

    def teardown_method(self):
        self.stats.close_spider(self.spider, "")
