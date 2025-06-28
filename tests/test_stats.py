from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from scrapy.extensions.corestats import CoreStats
from scrapy.spiders import Spider
from scrapy.statscollectors import DummyStatsCollector, StatsCollector
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


@pytest.fixture
def crawler() -> Crawler:
    return get_crawler(Spider)


@pytest.fixture
def spider(crawler: Crawler) -> Spider:
    return crawler._create_spider("foo")


class TestCoreStatsExtension:
    @mock.patch("scrapy.extensions.corestats.datetime")
    def test_core_stats_default_stats_collector(
        self, mock_datetime: mock.Mock, crawler: Crawler, spider: Spider
    ) -> None:
        fixed_datetime = datetime(2019, 12, 1, 11, 38)
        mock_datetime.now = mock.Mock(return_value=fixed_datetime)
        crawler.stats = StatsCollector(crawler)
        ext = CoreStats.from_crawler(crawler)
        ext.spider_opened(spider)
        ext.item_scraped({}, spider)
        ext.response_received(spider)
        ext.item_dropped({}, spider, ZeroDivisionError())
        ext.spider_closed(spider, "finished")
        assert ext.stats._stats == {
            "start_time": fixed_datetime,
            "finish_time": fixed_datetime,
            "item_scraped_count": 1,
            "response_received_count": 1,
            "item_dropped_count": 1,
            "item_dropped_reasons_count/ZeroDivisionError": 1,
            "finish_reason": "finished",
            "elapsed_time_seconds": 0.0,
        }

    def test_core_stats_dummy_stats_collector(
        self, crawler: Crawler, spider: Spider
    ) -> None:
        crawler.stats = DummyStatsCollector(crawler)
        ext = CoreStats.from_crawler(crawler)
        ext.spider_opened(spider)
        ext.item_scraped({}, spider)
        ext.response_received(spider)
        ext.item_dropped({}, spider, ZeroDivisionError())
        ext.spider_closed(spider, "finished")
        assert ext.stats._stats == {}


class TestStatsCollector:
    def test_collector(self, crawler: Crawler) -> None:
        stats = StatsCollector(crawler)
        assert stats.get_stats() == {}
        assert stats.get_value("anything") is None
        assert stats.get_value("anything", "default") == "default"
        stats.set_value("test", "value")
        assert stats.get_stats() == {"test": "value"}
        stats.set_value("test2", 23)
        assert stats.get_stats() == {"test": "value", "test2": 23}
        assert stats.get_value("test2") == 23
        stats.inc_value("test2")
        assert stats.get_value("test2") == 24
        stats.inc_value("test2", 6)
        assert stats.get_value("test2") == 30
        stats.max_value("test2", 6)
        assert stats.get_value("test2") == 30
        stats.max_value("test2", 40)
        assert stats.get_value("test2") == 40
        stats.max_value("test3", 1)
        assert stats.get_value("test3") == 1
        stats.min_value("test2", 60)
        assert stats.get_value("test2") == 40
        stats.min_value("test2", 35)
        assert stats.get_value("test2") == 35
        stats.min_value("test4", 7)
        assert stats.get_value("test4") == 7

    def test_dummy_collector(self, crawler: Crawler, spider: Spider) -> None:
        stats = DummyStatsCollector(crawler)
        assert stats.get_stats() == {}
        assert stats.get_value("anything") is None
        assert stats.get_value("anything", "default") == "default"
        stats.set_value("test", "value")
        stats.inc_value("v1")
        stats.max_value("v2", 100)
        stats.min_value("v3", 100)
        stats.open_spider(spider)
        stats.set_value("test", "value", spider=spider)
        assert stats.get_stats() == {}
        assert stats.get_stats(spider) == {}
