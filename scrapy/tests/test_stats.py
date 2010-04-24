import unittest 

from scrapy.spider import BaseSpider
from scrapy.xlib.pydispatch import dispatcher
from scrapy.stats.collector import StatsCollector, DummyStatsCollector
from scrapy.stats.signals import stats_spider_opened, stats_spider_closing, \
    stats_spider_closed

class StatsCollectorTest(unittest.TestCase):

    def setUp(self):
        self.spider = BaseSpider('foo')

    def test_collector(self):
        stats = StatsCollector()
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
        stats = DummyStatsCollector()
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

    def test_signals(self):
        signals_catched = set()

        def spider_opened(spider):
            assert spider is self.spider
            signals_catched.add(stats_spider_opened)

        def spider_closing(spider, reason):
            assert spider is self.spider
            assert reason == 'testing'
            signals_catched.add(stats_spider_closing)

        def spider_closed(spider, reason, spider_stats):
            assert spider is self.spider
            assert reason == 'testing'
            assert spider_stats == {'test': 1}
            signals_catched.add(stats_spider_closed)

        dispatcher.connect(spider_opened, signal=stats_spider_opened)
        dispatcher.connect(spider_closing, signal=stats_spider_closing)
        dispatcher.connect(spider_closed, signal=stats_spider_closed)

        stats = StatsCollector()
        stats.open_spider(self.spider)
        stats.set_value('test', 1, spider=self.spider)
        self.assertEqual([(self.spider, {'test': 1})], list(stats.iter_spider_stats()))
        stats.close_spider(self.spider, 'testing')
        assert stats_spider_opened in signals_catched
        assert stats_spider_closing in signals_catched
        assert stats_spider_closed in signals_catched

        dispatcher.disconnect(spider_opened, signal=stats_spider_opened)
        dispatcher.disconnect(spider_closing, signal=stats_spider_closing)
        dispatcher.disconnect(spider_closed, signal=stats_spider_closed)

if __name__ == "__main__":
    unittest.main()
