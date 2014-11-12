import unittest

from scrapy.spider import Spider
from scrapy.statscol import StatsCollector, DummyStatsCollector
from scrapy.utils.test import get_crawler

class StatsCollectorTest(unittest.TestCase):

    def setUp(self):
        self.crawler = get_crawler(Spider)
        self.spider = self.crawler._create_spider('foo')

    def test_collector(self):
        stats = StatsCollector(self.crawler)
        self.assertEqual(stats.get_stats(), {})
        self.assertEqual(stats.get_value('anything'), None)
        self.assertEqual(stats.get_value('anything', 'default'), 'default')
        stats.set_value('test', 'value')
        self.assertEqual(stats.get_stats(), {'test': 'value'})
        stats.set_value('test2', 23)
        self.assertEqual(stats.get_stats(), {'test': 'value', 'test2': 23})
        self.assertEqual(stats.get_value('test2'), 23)
        stats.inc_value('test2')
        self.assertEqual(stats.get_value('test2'), 24)
        stats.inc_value('test2', 6)
        self.assertEqual(stats.get_value('test2'), 30)
        stats.max_value('test2', 6)
        self.assertEqual(stats.get_value('test2'), 30)
        stats.max_value('test2', 40)
        self.assertEqual(stats.get_value('test2'), 40)
        stats.max_value('test3', 1)
        self.assertEqual(stats.get_value('test3'), 1)
        stats.min_value('test2', 60)
        self.assertEqual(stats.get_value('test2'), 40)
        stats.min_value('test2', 35)
        self.assertEqual(stats.get_value('test2'), 35)
        stats.min_value('test4', 7)
        self.assertEqual(stats.get_value('test4'), 7)

    def test_dummy_collector(self):
        stats = DummyStatsCollector(self.crawler)
        self.assertEqual(stats.get_stats(), {})
        self.assertEqual(stats.get_value('anything'), None)
        self.assertEqual(stats.get_value('anything', 'default'), 'default')
        stats.set_value('test', 'value')
        stats.inc_value('v1')
        stats.max_value('v2', 100)
        stats.min_value('v3', 100)
        stats.open_spider('a')
        stats.set_value('test', 'value', spider=self.spider)
        self.assertEqual(stats.get_stats(), {})
        self.assertEqual(stats.get_stats('a'), {})

if __name__ == "__main__":
    unittest.main()
