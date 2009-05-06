from unittest import TestCase, main
from scrapy.conf import settings
from scrapy.stats.statscollector import StatsCollector

class StatsTest(TestCase):
    def test_stats(self):
        stats = StatsCollector(enabled=False)
        self.assertEqual(stats, {})
        self.assertEqual(stats.getpath('anything'), None)
        self.assertEqual(stats.getpath('anything', 'default'), 'default')
        stats.setpath('test', 'value')
        self.assertEqual(stats, {})

        stats = StatsCollector(enabled=True)
        self.assertEqual(stats, {})
        self.assertEqual(stats.getpath('anything'), None)
        self.assertEqual(stats.getpath('anything', 'default'), 'default')
        stats.setpath('test', 'value')
        self.assertEqual(stats, {'test': 'value'})
        stats.setpath('test2', 23)
        self.assertEqual(stats, {'test': 'value', 'test2': 23})
        stats.setpath('one/two', 'val2')
        self.assertEqual(stats, {'test': 'value', 'test2': 23, 'one': {'two': 'val2'}})
        self.assertEqual(stats.getpath('one/two'), 'val2')
        self.assertEqual(stats.getpath('one/three'), None)
        self.assertEqual(stats.getpath('one/three', 'four'), 'four')
        self.assertEqual(stats.getpath('one'), {'two': 'val2'})

        # nodes must contain either data or other nodes, but not both!
        self.assertRaises(TypeError, stats.setpath, 'one/two/three', 22)

        stats.delpath('test2')
        self.assertEqual(stats, {'test': 'value', 'one': {'two': 'val2'}})
        stats.delpath('one/two')
        self.assertEqual(stats, {'test': 'value', 'one': {}})
        stats.delpath('one')
        self.assertEqual(stats, {'test': 'value'})

        stats.setpath('one/other/three', 20)
        self.assertEqual(stats.getpath('one/other/three'), 20)
        stats.incpath('one/other/three')
        self.assertEqual(stats.getpath('one/other/three'), 21)
        stats.incpath('one/other/three', 4)
        self.assertEqual(stats.getpath('one/other/three'), 25)

        stats.incpath('one/newnode', 1)
        self.assertEqual(stats.getpath('one/newnode'), 1)
        stats.incpath('one/newnode', -1)
        self.assertEqual(stats.getpath('one/newnode'), 0)

if __name__ == "__main__":
    main()
