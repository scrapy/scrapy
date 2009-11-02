import unittest 

from scrapy.xlib.pydispatch import dispatcher
from scrapy.stats.collector import StatsCollector, DummyStatsCollector
from scrapy.stats.signals import stats_domain_opened, stats_domain_closing, \
    stats_domain_closed

class StatsCollectorTest(unittest.TestCase):

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
        stats.open_domain('a')
        stats.set_value('test', 'value', domain='a')
        self.assertEqual(stats.get_stats(), {})
        self.assertEqual(stats.get_stats('a'), {})

    def test_signals(self):
        signals_catched = set()

        def domain_opened(domain):
            assert domain == 'example.com'
            signals_catched.add(stats_domain_opened)

        def domain_closing(domain, reason):
            assert domain == 'example.com'
            assert reason == 'testing'
            signals_catched.add(stats_domain_closing)

        def domain_closed(domain, reason, domain_stats):
            assert domain == 'example.com'
            assert reason == 'testing'
            assert domain_stats == {'test': 1}
            signals_catched.add(stats_domain_closed)

        dispatcher.connect(domain_opened, signal=stats_domain_opened)
        dispatcher.connect(domain_closing, signal=stats_domain_closing)
        dispatcher.connect(domain_closed, signal=stats_domain_closed)

        stats = StatsCollector()
        stats.open_domain('example.com')
        stats.set_value('test', 1, domain='example.com')
        stats.close_domain('example.com', 'testing')
        assert stats_domain_opened in signals_catched
        assert stats_domain_closing in signals_catched
        assert stats_domain_closed in signals_catched

        dispatcher.disconnect(domain_open, signal=stats_domain_opened)
        dispatcher.disconnect(domain_closing, signal=stats_domain_closing)
        dispatcher.disconnect(domain_closed, signal=stats_domain_closed)

if __name__ == "__main__":
    unittest.main()
