from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Spider
from scrapy.extensions.logstats import LogStats
from scrapy.utils.asyncio import sleep
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.spiders import SimpleSpider
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


@pytest.fixture
def crawler() -> Crawler:
    crawler = get_crawler(SimpleSpider)
    crawler.spider = crawler._create_spider("spidey")
    return crawler


@pytest.fixture
def stats(crawler: Crawler) -> StatsCollector:
    stats = crawler.stats
    stats.set_value("response_received_count", 4802)
    stats.set_value("item_scraped_count", 3201)
    return stats


@coroutine_test
async def test_stats_calculations(crawler: Crawler, stats: StatsCollector) -> None:
    logstats = build_from_crawler(LogStats, crawler)

    with pytest.raises(AttributeError):
        logstats.pagesprev
    with pytest.raises(AttributeError):
        logstats.itemsprev

    assert crawler.spider
    logstats.spider_opened(crawler.spider)
    logstats.calculate_stats()
    assert logstats.pagesprev == 4802
    assert logstats.itemsprev == 3201

    logstats.calculate_stats()
    assert logstats.items == 3201
    assert logstats.pages == 4802
    assert logstats.irate == 0.0
    assert logstats.prate == 0.0
    assert logstats.pagesprev == 4802
    assert logstats.itemsprev == 3201

    # Simulate what happens after a minute
    stats.set_value("response_received_count", 5187)
    stats.set_value("item_scraped_count", 3492)
    logstats.calculate_stats()
    assert logstats.items == 3492
    assert logstats.pages == 5187
    assert logstats.irate == 291.0
    assert logstats.prate == 385.0
    assert logstats.pagesprev == 5187
    assert logstats.itemsprev == 3492

    # Simulate when spider closes after running for 30 mins
    stats.set_value("start_time", datetime.fromtimestamp(1655100172).astimezone(UTC))
    stats.set_value("finish_time", datetime.fromtimestamp(1655101972).astimezone(UTC))
    logstats.spider_closed(crawler.spider, "test reason")
    assert stats.get_value("responses_per_minute") == 172.9
    assert stats.get_value("items_per_minute") == 116.4


def test_stats_calculations_no_time(crawler: Crawler, stats: StatsCollector) -> None:
    """The stat values should be None since the start and finish time are
    not available.
    """
    logstats = build_from_crawler(LogStats, crawler)
    assert crawler.spider
    logstats.spider_closed(crawler.spider, "test reason")
    assert stats.get_value("responses_per_minute") is None
    assert stats.get_value("items_per_minute") is None


def test_stats_calculation_no_elapsed_time(
    crawler: Crawler, stats: StatsCollector
) -> None:
    """The stat values should be None since the elapsed time is 0."""
    logstats = build_from_crawler(LogStats, crawler)
    stats.set_value("start_time", datetime.fromtimestamp(1655100172).astimezone(UTC))
    stats.set_value("finish_time", datetime.fromtimestamp(1655100172).astimezone(UTC))
    assert crawler.spider
    logstats.spider_closed(crawler.spider, "test reason")
    assert stats.get_value("responses_per_minute") is None
    assert stats.get_value("items_per_minute") is None


class _SleepingSpider(Spider):
    name = "sleeping"

    async def start(self) -> AsyncIterator[Any]:
        await sleep(0.3)
        return
        yield


@pytest.mark.parametrize(("interval", "logged"), [(60, False), (0.1, True)])
@coroutine_test
async def test_first_line_after_interval(
    interval: float, logged: bool, caplog: pytest.LogCaptureFixture
) -> None:
    crawler = get_crawler(_SleepingSpider, {"LOGSTATS_INTERVAL": interval})
    with caplog.at_level(logging.INFO):
        await crawler.crawl_async()
    lines = [r for r in caplog.records if r.name == "scrapy.extensions.logstats"]
    assert bool(lines) is logged
