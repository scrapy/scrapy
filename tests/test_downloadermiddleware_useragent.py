from __future__ import annotations

from scrapy.downloadermiddlewares.useragent import UserAgentMiddleware
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


def get_spider_and_mw(
    default_useragent: str | None,
) -> tuple[Spider, UserAgentMiddleware]:
    crawler = get_crawler(Spider, {"USER_AGENT": default_useragent})
    spider = crawler._create_spider("foo")
    return spider, UserAgentMiddleware.from_crawler(crawler)


def test_default_agent():
    _, mw = get_spider_and_mw("default_useragent")
    req = Request("http://scrapytest.org/")
    assert mw.process_request(req) is None
    assert req.headers["User-Agent"] == b"default_useragent"


def test_header_agent():
    spider, mw = get_spider_and_mw("default_useragent")
    mw.spider_opened(spider)
    req = Request("http://scrapytest.org/", headers={"User-Agent": "header_useragent"})
    assert mw.process_request(req) is None
    assert req.headers["User-Agent"] == b"header_useragent"


def test_no_agent():
    spider, mw = get_spider_and_mw(None)
    mw.spider_opened(spider)
    req = Request("http://scrapytest.org/")
    assert mw.process_request(req) is None
    assert "User-Agent" not in req.headers
