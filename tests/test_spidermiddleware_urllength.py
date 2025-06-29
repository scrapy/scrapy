from __future__ import annotations

from logging import INFO
from typing import TYPE_CHECKING

import pytest

from scrapy.http import Request, Response
from scrapy.spidermiddlewares.urllength import UrlLengthMiddleware
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


maxlength = 25
response = Response("http://scrapytest.org")
short_url_req = Request("http://scrapytest.org/")
long_url_req = Request("http://scrapytest.org/this_is_a_long_url")
reqs: list[Request] = [short_url_req, long_url_req]


@pytest.fixture
def crawler() -> Crawler:
    return get_crawler(Spider, {"URLLENGTH_LIMIT": maxlength})


@pytest.fixture
def spider(crawler: Crawler) -> Spider:
    return crawler._create_spider("foo")


@pytest.fixture
def stats(crawler: Crawler) -> StatsCollector:
    assert crawler.stats is not None
    return crawler.stats


@pytest.fixture
def mw(crawler: Crawler) -> UrlLengthMiddleware:
    return UrlLengthMiddleware.from_crawler(crawler)


def process_spider_output(mw: UrlLengthMiddleware, spider: Spider) -> list[Request]:
    return list(mw.process_spider_output(response, reqs, spider))


def test_middleware_works(mw: UrlLengthMiddleware, spider: Spider) -> None:
    assert process_spider_output(mw, spider) == [short_url_req]


def test_logging(
    stats: StatsCollector,
    mw: UrlLengthMiddleware,
    spider: Spider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(INFO):
        process_spider_output(mw, spider)
    ric = stats.get_value("urllength/request_ignored_count", spider=spider)
    assert ric == 1
    assert f"Ignoring link (url length > {maxlength})" in caplog.text
