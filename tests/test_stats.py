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
        mock_datetime.utcnow = mock.Mock(return_value=fixed_datetime)
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

    def test_collector_1(self):
        stats = StatsCollector(self.crawler)
        self.assertEqual(stats.get_stats(), {})

    def test_collector_2(self):
        stats = StatsCollector(self.crawler)
        self.assertEqual(stats.get_value("anything"), None)

    def test_collector_3(self):
        stats = StatsCollector(self.crawler)
        self.assertEqual(stats.get_value("anything", "default"), "default")

    def test_collector_4(self):
        stats = StatsCollector(self.crawler)
        stats.set_value("test", "value")
        self.assertEqual(stats.get_stats(), {"test": "value"})

    def test_collector_5(self):
        stats = StatsCollector(self.crawler)
        stats.set_value("test5", 23)
        self.assertEqual(stats.get_stats(), {"test5": 23})

    def test_collector_6(self):
        stats = StatsCollector(self.crawler)
        stats.set_value("test6", 23)
        self.assertEqual(stats.get_value("test6"), 23)

    def test_collector_7(self):
        stats = StatsCollector(self.crawler)
        stats.set_value("test7", 23)
        stats.inc_value("test7")
        self.assertEqual(stats.get_value("test7"), 24)

    def test_collector_8(self):
        stats = StatsCollector(self.crawler)
        stats.set_value("test8", 24)
        stats.inc_value("test8", 6)
        self.assertEqual(stats.get_value("test8"), 30)

    def test_collector_9(self):
        stats = StatsCollector(self.crawler)
        stats.set_value("test9", 24)
        stats.max_value("test9", 6)
        self.assertEqual(stats.get_value("test9"), 24)

    def test_collector_10(self):
        stats = StatsCollector(self.crawler)
        stats.max_value("test10", 40)
        self.assertEqual(stats.get_value("test10"), 40)

    def test_collector_11(self):
        stats = StatsCollector(self.crawler)
        stats.max_value("test11", 1)
        self.assertEqual(stats.get_value("test11"), 1)

    def test_collector_12(self):
        stats = StatsCollector(self.crawler)
        stats.set_value("test12", 40)
        stats.min_value("test12", 60)
        self.assertEqual(stats.get_value("test12"), 60)

    def test_collector_13(self):
        stats = StatsCollector(self.crawler)
        stats.min_value("test13", 35)
        self.assertEqual(stats.get_value("test13"), 35)

    def test_collector_14(self):
        stats = StatsCollector(self.crawler)
        stats.min_value("test14", 7)
        self.assertEqual(stats.get_value("test14"), 7)

    def test_dummy_collector_1(self):
        stats = DummyStatsCollector(self.crawler)
        self.assertEqual(stats.get_stats(), {})

    def test_dummy_collector_2(self):
        stats = DummyStatsCollector(self.crawler)
        self.assertEqual(stats.get_value("anything"), None)

    def test_dummy_collector_3(self):
        stats = DummyStatsCollector(self.crawler)
        self.assertEqual(stats.get_value("anything", "default"), "default")

    def test_dummy_collector_4(self):
        stats = DummyStatsCollector(self.crawler)
        stats.set_value("test", "value")
        stats.inc_value("v1")
        stats.max_value("v2", 100)
        stats.min_value("v3", 100)
        stats.open_spider("a")
        stats.set_value("test", "value", spider=self.spider)
        self.assertEqual(stats.get_stats(), {})

    def test_dummy_collector_5(self):
        stats = DummyStatsCollector(self.crawler)
        stats.set_value("test", "value")
        stats.inc_value("v1")
        stats.max_value("v2", 100)
        stats.min_value("v3", 100)
        stats.open_spider("a")
        stats.set_value("test", "value", spider=self.spider)
        self.assertEqual(stats.get_stats("a"), {})


if __name__ == "__main__":
    unittest.main()
