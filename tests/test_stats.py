import unittest
from datetime import datetime
from unittest import mock

from scrapy.extensions.corestats import CoreStats
from scrapy.spiders import Spider
from scrapy.statscollectors import DummyStatsCollector, StatsCollector
from scrapy.utils.test import get_crawler


class CoreStatsExtensionTest(unittest.TestCase):
    def setUp(self):
        self.crawler = get_crawler(Spider)
        self.spider = self.crawler._create_spider("foo")

    @mock.patch("scrapy.extensions.corestats.datetime")
    def test_core_stats_default_stats_collector(self, mock_datetime):
        fixed_datetime = datetime(2019, 12, 1, 11, 38)
        mock_datetime.now = mock.Mock(return_value=fixed_datetime)
        self.crawler.stats = StatsCollector(self.crawler)
        ext = CoreStats.from_crawler(self.crawler)
        ext.spider_opened(self.spider)
        ext.item_scraped({}, self.spider)
        ext.response_received(self.spider)
        ext.item_dropped({}, self.spider, ZeroDivisionError())
        ext.spider_closed(self.spider, "finished")
        self.assertEqual(
            ext.stats._stats,
            {
                "start_time": fixed_datetime,
                "finish_time": fixed_datetime,
                "item_scraped_count": 1,
                "response_received_count": 1,
                "item_dropped_count": 1,
                "item_dropped_reasons_count/ZeroDivisionError": 1,
                "finish_reason": "finished",
                "elapsed_time_seconds": 0.0,
            },
        )

    def test_core_stats_dummy_stats_collector(self):
        self.crawler.stats = DummyStatsCollector(self.crawler)
        ext = CoreStats.from_crawler(self.crawler)
        ext.spider_opened(self.spider)
        ext.item_scraped({}, self.spider)
        ext.response_received(self.spider)
        ext.item_dropped({}, self.spider, ZeroDivisionError())
        ext.spider_closed(self.spider, "finished")
        self.assertEqual(ext.stats._stats, {})


class StatsCollectorTest(unittest.TestCase):
    def setUp(self):
        self.crawler = get_crawler(Spider)
        self.spider = self.crawler._create_spider("foo")

    def test_collector(self):
        stats = StatsCollector(self.crawler)
        self.assertEqual(stats.get_stats(), {})
        self.assertEqual(stats.get_value("anything"), None)
        self.assertEqual(stats.get_value("anything", "default"), "default")
        stats.set_value("test", "value")
        self.assertEqual(stats.get_stats(), {"test": "value"})
        stats.set_value("test2", 23)
        self.assertEqual(stats.get_stats(), {"test": "value", "test2": 23})
        self.assertEqual(stats.get_value("test2"), 23)
        stats.inc_value("test2")
        self.assertEqual(stats.get_value("test2"), 24)
        stats.inc_value("test2", 6)
        self.assertEqual(stats.get_value("test2"), 30)
        stats.max_value("test2", 6)
        self.assertEqual(stats.get_value("test2"), 30)
        stats.max_value("test2", 40)
        self.assertEqual(stats.get_value("test2"), 40)
        stats.max_value("test3", 1)
        self.assertEqual(stats.get_value("test3"), 1)
        stats.min_value("test2", 60)
        self.assertEqual(stats.get_value("test2"), 40)
        stats.min_value("test2", 35)
        self.assertEqual(stats.get_value("test2"), 35)
        stats.min_value("test4", 7)
        self.assertEqual(stats.get_value("test4"), 7)

    def test_dummy_collector(self):
        stats = DummyStatsCollector(self.crawler)
        self.assertEqual(stats.get_stats(), {})
        self.assertEqual(stats.get_value("anything"), None)
        self.assertEqual(stats.get_value("anything", "default"), "default")
        stats.set_value("test", "value")
        stats.inc_value("v1")
        stats.max_value("v2", 100)
        stats.min_value("v3", 100)
        stats.open_spider("a")
        stats.set_value("test", "value", spider=self.spider)
        self.assertEqual(stats.get_stats(), {})
        self.assertEqual(stats.get_stats("a"), {})
