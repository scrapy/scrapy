import unittest
import os
import json

from scrapy.spider import BaseSpider
from scrapy.statscol import StatsCollector, DummyStatsCollector, JsonStatsCollector
from scrapy.utils.test import get_crawler


stats_file = '/tmp/dump.json'


class StatsCollectorTest(unittest.TestCase):

    def setUp(self):
        self.crawler = get_crawler()
        self.spider = BaseSpider('foo')

    def tearDown(self):
        try:
            os.unlink(stats_file)
        except OSError:
            pass

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

    def test_json_dump(self):
        self.crawler.settings.values['STATS_FILE'] = stats_file
        stats = JsonStatsCollector(self.crawler)
        self.assertEqual(stats.get_stats(), {})
        self.assertEqual(stats.get_value('anything'), None)
        self.assertEqual(stats.get_value('anything', 'default'), 'default')
        stats.set_value('test', 'value')
        stats.inc_value('v1')
        stats.max_value('v2', 100)
        stats.min_value('v3', 100)
        stats.open_spider('a')
        stats.close_spider('a', 'cause')

        self.assertTrue(os.path.exists(stats_file))
        #test the dump loading
        with open(stats_file) as f:
            stats_dump = json.load(f)
            self.assertIn('v1', stats_dump)
            self.assertIn('v2', stats_dump)
            self.assertIn('v3', stats_dump)
            self.assertEqual(stats_dump['v1'], 1)
            self.assertEqual(stats_dump['v2'], 100)
            self.assertEqual(stats_dump['v3'], 100)


if __name__ == "__main__":
    unittest.main()
