from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scrapy.http import Request, Response
from scrapy.spidermiddlewares.depth import DepthMiddleware
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from collections.abc import Generator

    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


@pytest.fixture
def crawler() -> Crawler:
    return get_crawler(Spider, {"DEPTH_LIMIT": 1, "DEPTH_STATS_VERBOSE": True})


@pytest.fixture
def spider(crawler: Crawler) -> Spider:
    crawler.spider = crawler._create_spider("scrapytest.org")
    return crawler.spider


@pytest.fixture
def stats(crawler: Crawler, spider: Spider) -> Generator[StatsCollector]:
    assert crawler.stats is not None
    crawler.stats.open_spider(spider)

    yield crawler.stats

    crawler.stats.close_spider(spider, "")


@pytest.fixture
def mw(crawler: Crawler) -> DepthMiddleware:
    return DepthMiddleware.from_crawler(crawler)


def test_process_spider_output(
    mw: DepthMiddleware, stats: StatsCollector, spider: Spider
) -> None:
    req = Request("http://scrapytest.org")
    resp = Response("http://scrapytest.org")
    resp.request = req
    result = [Request("http://scrapytest.org")]

    out = list(mw.process_spider_output(resp, result, spider))
    assert out == result

    rdc = stats.get_value("request_depth_count/1", spider=spider)
    assert rdc == 1

    req.meta["depth"] = 1

    out2 = list(mw.process_spider_output(resp, result, spider))
    assert not out2

    rdm = stats.get_value("request_depth_max", spider=spider)
    assert rdm == 1
