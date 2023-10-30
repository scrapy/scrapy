from unittest import TestCase

from scrapy.downloadermiddlewares.useragent import UserAgentMiddleware
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


class UserAgentMiddlewareTest(TestCase):
    def get_spider_and_mw(self, default_useragent):
        crawler = get_crawler(Spider, {"USER_AGENT": default_useragent})
        spider = crawler._create_spider("foo")
        return spider, UserAgentMiddleware.from_crawler(crawler)

    def test_default_agent(self):
        spider, mw = self.get_spider_and_mw("default_useragent")
        req = Request("http://scrapytest.org/")
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.headers["User-Agent"], b"default_useragent")

    def test_remove_agent(self):
        # settings USER_AGENT to None should remove the user agent
        spider, mw = self.get_spider_and_mw("default_useragent")
        spider.user_agent = None
        mw.spider_opened(spider)
        req = Request("http://scrapytest.org/")
        assert mw.process_request(req, spider) is None
        assert req.headers.get("User-Agent") is None

    def test_spider_agent(self):
        spider, mw = self.get_spider_and_mw("default_useragent")
        spider.user_agent = "spider_useragent"
        mw.spider_opened(spider)
        req = Request("http://scrapytest.org/")
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.headers["User-Agent"], b"spider_useragent")

    def test_header_agent(self):
        spider, mw = self.get_spider_and_mw("default_useragent")
        spider.user_agent = "spider_useragent"
        mw.spider_opened(spider)
        req = Request(
            "http://scrapytest.org/", headers={"User-Agent": "header_useragent"}
        )
        assert mw.process_request(req, spider) is None
        self.assertEqual(req.headers["User-Agent"], b"header_useragent")

    def test_no_agent(self):
        spider, mw = self.get_spider_and_mw(None)
        spider.user_agent = None
        mw.spider_opened(spider)
        req = Request("http://scrapytest.org/")
        assert mw.process_request(req, spider) is None
        assert "User-Agent" not in req.headers
