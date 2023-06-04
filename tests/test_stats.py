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
        """
        Test case method to test if when initializing a 
        stats collector the stats are an empty dictionary. 
        """
        stats = StatsCollector(self.crawler)
        self.assertEqual(stats.get_stats(), {})

    def test_collector_2(self):
        """
        Test case to check if setting up a stats collector
        with no data returns none when asked for its value.
        """
        stats = StatsCollector(self.crawler)
        self.assertEqual(stats.get_value("anything"), None)

    def test_collector_3(self):
        """
        Test case to test if a stats collector is given default value
        retunns default as its value
        """
        stats = StatsCollector(self.crawler)
        self.assertEqual(stats.get_value("anything", "default"), "default")

    def test_collector_4(self):
        """
        Test case to tets if a test collector is set to have value 
        as value it will return value when asked for its stats. 
        """
        stats = StatsCollector(self.crawler)
        stats.set_value("test", "value")
        self.assertEqual(stats.get_stats(), {"test": "value"})

    def test_collector_5(self):
        """"
        Test case to check if set_value function for a stats collector
        successfully sets the stats value to 23. 
        """
        stats = StatsCollector(self.crawler)
        stats.set_value("test5", 23)
        self.assertEqual(stats.get_stats(), {"test5": 23})

    def test_collector_6(self):
        """
        Test case to check if setting stats value to 26 
        successfully returns 26
        """
        stats = StatsCollector(self.crawler)
        stats.set_value("test6", 23)
        self.assertEqual(stats.get_value("test6"), 23)

    def test_collector_7(self):
        """
        Test case to check if setting calue to 23 and using 
        inc_value to increase value successfully return the 
        value 24
        """
        stats = StatsCollector(self.crawler)
        stats.set_value("test7", 23)
        stats.inc_value("test7")
        self.assertEqual(stats.get_value("test7"), 24)

    def test_collector_8(self):
        """
        Test case to confirm that setting the value to 24 
        and then increasing the stats_value by 6 successfully 
        returns the value 30.
        """
        stats = StatsCollector(self.crawler)
        stats.set_value("test8", 24)
        stats.inc_value("test8", 6)
        self.assertEqual(stats.get_value("test8"), 30)

    def test_collector_9(self):
        """
        Test case to check if setting the stats value to have
        maximum value of 6 changes the result of the stats value
        that was set using set_value. 
        """
        stats = StatsCollector(self.crawler)
        stats.set_value("test9", 24)
        stats.max_value("test9", 6)
        self.assertEqual(stats.get_value("test9"), 24)

    def test_collector_10(self):
        """
        Test if setting stats max value to 40 successfully
        sets the value to 40.
        """
        stats = StatsCollector(self.crawler)
        stats.max_value("test10", 40)
        self.assertEqual(stats.get_value("test10"), 40)

    def test_collector_11(self):
        """
        Test if setting stats max value to 1 successfully 
        sets the value to 1. 
        """
        stats = StatsCollector(self.crawler)
        stats.max_value("test11", 1)
        self.assertEqual(stats.get_value("test11"), 1)

    def test_collector_12(self):
        """
        Test if setting min_value for an instance of 
        stats collector to 60 successfully sets the value
        to 60
        """
        stats = StatsCollector(self.crawler)
        stats.set_value("test12", 40)
        stats.min_value("test12", 60)
        self.assertEqual(stats.get_value("test12"), 40)

    def test_collector_13(self):
        """
        Test if setting the min value for an instance of 
        stats collector to 35 without previously setting any
        other value successfully sets the stats value to 35
        """
        stats = StatsCollector(self.crawler)
        stats.min_value("test13", 35)
        self.assertEqual(stats.get_value("test13"), 35)

    def test_collector_14(self):
        """
        Tests if setting the min_value for stats collector 
        to 7 without previously setting to another value 
        successfully sets the value to 7
        """
        stats = StatsCollector(self.crawler)
        stats.min_value("test14", 7)
        self.assertEqual(stats.get_value("test14"), 7)

    def test_dummy_collector_1(self):
        """
        Tests if initializing an instance of dummy stats
        collector successfully returns an empty dictionary 
        if no previous data were passed when we ask for the stats
        of the dummy stats collector. 
        """
        stats = DummyStatsCollector(self.crawler)
        self.assertEqual(stats.get_stats(), {})

    def test_dummy_collector_2(self):
        """
        Tests if no values was set for a dummy stats
        collector. The return value is None.
        """
        stats = DummyStatsCollector(self.crawler)
        self.assertEqual(stats.get_value("anything"), None)

    def test_dummy_collector_3(self):
        """
        Tests if no value has been set for a dummy stats collector
        when ask for a value with default setting it returns default.
        """
        stats = DummyStatsCollector(self.crawler)
        self.assertEqual(stats.get_value("anything", "default"), "default")

    def test_dummy_collector_4(self):
        """
        Tests if changing the value of a dummy stats collector
        multiple times, will result to always keep the last value 
        that the dummy stats collector was set. 
        """
        stats = DummyStatsCollector(self.crawler)
        stats.set_value("test", "value")
        stats.inc_value("v1")
        stats.max_value("v2", 100)
        stats.min_value("v3", 100)
        stats.open_spider("a")
        stats.set_value("test", "value", spider=self.spider)
        self.assertEqual(stats.get_stats(), {})

    def test_dummy_collector_5(self):
        """
        Test that when opening a new spider instance from a 
        dummy stats collector instance, the initialize value is 
        an empty dictionary for the stats of the new spider instance
        """
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
