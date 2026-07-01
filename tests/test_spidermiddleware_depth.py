from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scrapy.http import Request, Response
from scrapy.spidermiddlewares.depth import DepthMiddleware
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from collections.abc import Generator

    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


@pytest.fixture
def crawler() -> Crawler:
    return get_crawler(Spider, {"DEPTH_LIMIT": 1, "DEPTH_STATS_VERBOSE": True})


@pytest.fixture
def stats(crawler: Crawler) -> Generator[StatsCollector]:
    assert crawler.stats is not None
    crawler.stats.open_spider()

    yield crawler.stats

    crawler.stats.close_spider()


@pytest.fixture
def mw(crawler: Crawler) -> DepthMiddleware:
    return DepthMiddleware.from_crawler(crawler)


def test_process_spider_output(mw: DepthMiddleware, stats: StatsCollector) -> None:
    req = Request("http://scrapytest.org")
    resp = Response("http://scrapytest.org")
    resp.request = req
    result = [Request("http://scrapytest.org")]

    out = list(mw.process_spider_output(resp, result))
    assert out == result

    rdc = stats.get_value("request_depth_count/1")
    assert rdc == 1

    req.meta["depth"] = 1

    out2 = list(mw.process_spider_output(resp, result))
    assert not out2

    rdm = stats.get_value("request_depth_max")
    assert rdm == 1


def test_priority_and_non_verbose_stats() -> None:
    crawler = get_crawler(
        Spider,
        {"DEPTH_LIMIT": 0, "DEPTH_STATS_VERBOSE": False, "DEPTH_PRIORITY": 10},
    )
    assert crawler.stats is not None
    crawler.stats.open_spider()
    try:
        mw = build_from_crawler(DepthMiddleware, crawler)
        resp = Response("http://toscrape.com")
        resp.request = Request("http://toscrape.com")
        resp.request.meta["depth"] = 2
        out = list(mw.process_spider_output(resp, [Request("http://toscrape.com")]))
        assert len(out) == 1
        # priority is decremented by depth * DEPTH_PRIORITY
        assert out[0].priority == -30
        assert out[0].meta["depth"] == 3
        # non-verbose stats don't track per-depth counts but still track the max
        assert crawler.stats.get_value("request_depth_count/3") is None
        assert crawler.stats.get_value("request_depth_max") == 3
    finally:
        crawler.stats.close_spider()
