import unittest

from scrapy.spider import Spider
from scrapy.contrib import periodicstats
from scrapy.utils.test import get_crawler
from scrapy.exceptions import NotConfigured


class CollectorTestManager(object):
    def __init__(self, settings_dict=None):
        self.crawler = get_crawler(Spider, settings_dict=settings_dict)
        self.spider = self.crawler._create_spider('foo')
        self.collector = periodicstats.Collector(self.crawler)

    def run_interval(self, is_close=False):
        return self.collector._process_interval_stats(self.spider, is_close=is_close)

    def run_sequence(self, operations_sequence, expected_stats_sequence):
        operations_list = self._sequence_as_values_list(operations_sequence)
        expected_stats_list = self._sequence_as_values_list(expected_stats_sequence)
        for i, (operations, expected_stats) in enumerate(zip(operations_list, expected_stats_list)):
            self._add_interval_operations(operations)
            iteration_stats = self.run_interval(is_close=(i == len(operations_list)-1))
            yield i+1, iteration_stats, expected_stats

    def _add_interval_operations(self, operations):
        for key, value in operations.iteritems():
            if isinstance(value, bool):
                if value is not None:
                    self.collector.set_value(key, value)
            elif isinstance(value, int):
                if value:
                    self.collector.inc_value(key, value)
            elif value is not None:
                self.collector.set_value(key, value)

    def _sequence_as_values_list(self, sequence):
        values_list = []
        n_iterations = max([len(l) for l in sequence.values()])
        for i in range(n_iterations):
            values = {}
            for key, data in sequence.iteritems():
                value = data[i]
                if value is not None:
                    values[key] = value
            values_list.append(values)
        return values_list


OPERATIONS_SEQUENCE = {
    #    ------------------------------------------------------------------------------------------
    #        1        2        3        4        5        6        7        8        9       10
    #    ------------------------------------------------------------------------------------------
    "A": [  None ,     10 ,      3 ,   None ,      5 ,     10 ,      4 ,   None ,   None ,      8 ],
    "B": [     5 ,      5 ,     10 ,     10 ,    -20 ,    -20 ,     10 ,     10 ,     50 ,     50 ],
    "C": [  None ,      1 ,      2 ,   None ,      1 ,     -1 ,      0 ,      1 ,      2 ,      0 ],
    "D": [  None ,   True ,  False ,   True ,   True ,   True ,  False ,  False ,  False ,   True ],
    "E": ['black', 'white', 'black', 'white', 'white',   None ,   None , 'white', 'black', 'white'],
    "F": [  None ,   None ,   'abc',   None ,   'def',   None ,   None ,   None ,   None ,   None ],
    #    -----------------------------------------------------------------------------------------
}


def extract_subsequence(keys, sequence):
    return dict([(key, sequence[key]) for key in keys])

OPERATIONS_SEQUENCE_A = extract_subsequence('A', OPERATIONS_SEQUENCE)
OPERATIONS_SEQUENCE_B = extract_subsequence('B', OPERATIONS_SEQUENCE)
OPERATIONS_SEQUENCE_C = extract_subsequence('C', OPERATIONS_SEQUENCE)
OPERATIONS_SEQUENCE_D = extract_subsequence('D', OPERATIONS_SEQUENCE)
OPERATIONS_SEQUENCE_E = extract_subsequence('E', OPERATIONS_SEQUENCE)
OPERATIONS_SEQUENCE_F = extract_subsequence('F', OPERATIONS_SEQUENCE)


class PeriodicStatsCollectorTest(unittest.TestCase):

    def assert_sequence(self, manager, operations_sequence, expected_stats_sequence):
        """
        Runs an operations sequence and asserts that returned stats are the expected ones for each interval
        """
        for i, iteration_stats, expected_stats in manager.run_sequence(operations_sequence, expected_stats_sequence):
            self.assertEqual(iteration_stats, expected_stats,
                             msg='wrong sequence in iteration #%d:\n'
                                 '     got: %s\n'
                                 'expected: %s' %
                                 (i, iteration_stats, expected_stats))

    def test_basic_collector(self):
        """
        Tests base scrapy stats collector
        """
        manager = CollectorTestManager()
        stats = manager.collector
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

    def test_default(self):
        """
        Tests default collector
        """
        manager = CollectorTestManager()
        manager.collector.set_value('test', 'value')
        self.assertEqual(manager.run_interval(), {})
        self.assertEqual(manager.run_interval(is_close=True), {})

    def test_sequence_default(self):
        """
        Tests sequence with default collector
        """
        manager = CollectorTestManager({
            'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='A'),
                periodicstats.Observer(key='B'),
                periodicstats.Observer(key='C'),
                periodicstats.Observer(key='D'),
                periodicstats.Observer(key='E'),
                periodicstats.Observer(key='F'),
            ]
        })
        expected_stats_sequence = {
            #    ------------------------------------------------------------------------------------------
            #        1        2        3        4        5        6        7        8        9       10
            #    ------------------------------------------------------------------------------------------
            "A": [  None ,     10 ,     13 ,     13 ,     18 ,     28 ,     32 ,     32 ,     32 ,     40 ],
            "B": [     5 ,     10 ,     20 ,     30 ,     10 ,    -10 ,      0 ,     10 ,     60 ,    110 ],
            "C": [  None ,      1 ,      3 ,      3 ,      4 ,      3 ,      3 ,      4 ,      6 ,      6 ],
            "D": [  None ,   True ,  False ,   True ,   True ,   True ,  False ,  False ,  False ,   True ],
            "E": ['black', 'white', 'black', 'white', 'white', 'white', 'white', 'white', 'black', 'white'],
            "F": [  None ,   None ,   'abc',  'abc' ,   'def',   'def',   'def',   'def',   'def',   'def'],
            #    ------------------------------------------------------------------------------------------
        }
        self.assert_sequence(
            manager=manager,
            operations_sequence=OPERATIONS_SEQUENCE,
            expected_stats_sequence=expected_stats_sequence
        )

    def test_sequence_filtering(self):
        """
        Tests observer key filtering
        """
        manager = CollectorTestManager({
            'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='A'),
                periodicstats.Observer(key='C'),
                periodicstats.Observer(key='F'),
            ]
        })
        expected_stats_sequence = {
            #    ------------------------------------------------------------------------------------------
            #        1        2        3        4        5        6        7        8        9       10
            #    ------------------------------------------------------------------------------------------
            "A": [  None ,     10 ,     13 ,     13 ,     18 ,     28 ,     32 ,     32 ,     32 ,     40 ],
            "C": [  None ,      1 ,      3 ,      3 ,      4 ,      3 ,      3 ,      4 ,      6 ,      6 ],
            "F": [  None ,   None ,   'abc',  'abc' ,   'def',   'def',   'def',   'def',   'def',   'def'],
            #    ------------------------------------------------------------------------------------------
        }
        self.assert_sequence(
            manager=manager,
            operations_sequence=OPERATIONS_SEQUENCE,
            expected_stats_sequence=expected_stats_sequence
        )

    def test_sequence_export_key(self):
        """
        Tests sequence + export keys
        """
        manager = CollectorTestManager({
            'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='A', export_key='a'),
                periodicstats.Observer(key='B', export_key='b'),
                periodicstats.Observer(key='C', export_key='c'),
                periodicstats.Observer(key='D', export_key='d'),
                periodicstats.Observer(key='E', export_key='e'),
                periodicstats.Observer(key='F', export_key='f'),
            ]
        })
        expected_stats_sequence = {
            #    ------------------------------------------------------------------------------------------
            #        1        2        3        4        5        6        7        8        9       10
            #    ------------------------------------------------------------------------------------------
            "a": [  None ,     10 ,     13 ,     13 ,     18 ,     28 ,     32 ,     32 ,     32 ,     40 ],
            "b": [     5 ,     10 ,     20 ,     30 ,     10 ,    -10 ,      0 ,     10 ,     60 ,    110 ],
            "c": [  None ,      1 ,      3 ,      3 ,      4 ,      3 ,      3 ,      4 ,      6 ,      6 ],
            "d": [  None ,   True ,  False ,   True ,   True ,   True ,  False ,  False ,  False ,   True ],
            "e": ['black', 'white', 'black', 'white', 'white', 'white', 'white', 'white', 'black', 'white'],
            "f": [  None ,   None ,   'abc',  'abc' ,   'def',   'def',   'def',   'def',   'def',   'def'],
            #    ------------------------------------------------------------------------------------------
        }
        self.assert_sequence(
            manager=manager,
            operations_sequence=OPERATIONS_SEQUENCE,
            expected_stats_sequence=expected_stats_sequence
        )

    def test_sequence_partial_values(self):
        """
        Tests sequence + use_partial_values
        """
        manager = CollectorTestManager({
            'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='A', use_partial_values=True),
                periodicstats.Observer(key='B', use_partial_values=True),
                periodicstats.Observer(key='C', use_partial_values=True),
                periodicstats.Observer(key='D'),
                periodicstats.Observer(key='E'),
                periodicstats.Observer(key='F'),
            ]
        })
        expected_stats_sequence = {
            #    ------------------------------------------------------------------------------------------
            #        1        2        3        4        5        6        7        8        9       10
            #    ------------------------------------------------------------------------------------------
            "A": [  None ,     10 ,      3 ,      0 ,      5 ,     10 ,      4 ,      0 ,     0 ,       8 ],
            "B": [     5 ,      5 ,     10 ,     10 ,    -20 ,    -20 ,     10 ,     10 ,     50 ,     50 ],
            "C": [  None ,      1 ,      2 ,      0 ,      1 ,     -1 ,      0 ,      1 ,      2 ,      0 ],
            "D": [  None ,   True ,  False ,   True ,   True ,   True ,  False ,  False ,  False ,   True ],
            "E": ['black', 'white', 'black', 'white', 'white', 'white', 'white', 'white', 'black', 'white'],
            "F": [  None ,   None ,   'abc',  'abc' ,   'def',   'def',   'def',   'def',   'def',   'def'],
            #    ------------------------------------------------------------------------------------------
        }
        self.assert_sequence(
            manager=manager,
            operations_sequence=OPERATIONS_SEQUENCE,
            expected_stats_sequence=expected_stats_sequence
        )

    def test_sequence_only_export_on_change(self):
        """
        Tests sequence + only_export_on_change
        """
        manager = CollectorTestManager({
            'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='A', only_export_on_change=True),
                periodicstats.Observer(key='B', only_export_on_change=True),
                periodicstats.Observer(key='C', only_export_on_change=True),
                periodicstats.Observer(key='D', only_export_on_change=True),
                periodicstats.Observer(key='E', only_export_on_change=True),
                periodicstats.Observer(key='F', only_export_on_change=True),
            ]
        })
        expected_stats_sequence = {
            #    ------------------------------------------------------------------------------------------
            #        1        2        3        4        5        6        7        8        9       10
            #    ------------------------------------------------------------------------------------------
            "A": [  None ,     10 ,     13 ,   None ,     18 ,     28 ,     32 ,   None ,   None ,     40 ],
            "B": [     5 ,     10 ,     20 ,     30 ,     10 ,    -10 ,      0 ,     10 ,     60 ,    110 ],
            "C": [  None ,      1 ,      3 ,   None ,      4 ,      3 ,   None ,      4 ,      6 ,      6 ],
            "D": [  None ,   True ,  False ,   True ,   None ,   None ,  False ,   None ,   None ,   True ],
            "E": ['black', 'white', 'black', 'white',   None ,   None ,   None ,   None , 'black', 'white'],
            "F": [  None ,   None ,   'abc',   None ,   'def',   None ,   None ,   None ,   None ,   'def'],
            #    ------------------------------------------------------------------------------------------
        }
        self.assert_sequence(
            manager=manager,
            operations_sequence=OPERATIONS_SEQUENCE,
            expected_stats_sequence=expected_stats_sequence
        )

    def test_sequence_only_export_on_close(self):
        """
        Tests sequence + only_export_on_close
        """
        manager = CollectorTestManager({
            'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='A', only_export_on_close=True),
                periodicstats.Observer(key='B', only_export_on_close=True),
                periodicstats.Observer(key='C', only_export_on_close=True),
                periodicstats.Observer(key='D', only_export_on_close=True),
                periodicstats.Observer(key='E', only_export_on_close=True),
                periodicstats.Observer(key='F', only_export_on_close=True),
            ]
        })
        expected_stats_sequence = {
            #    ------------------------------------------------------------------------------------------
            #        1        2        3        4        5        6        7        8        9       10
            #    ------------------------------------------------------------------------------------------
            "A": [  None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,     40 ],
            "B": [  None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,    110 ],
            "C": [  None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,      6 ],
            "D": [  None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,   True ],
            "E": [  None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,   None , 'white'],
            "F": [  None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,   'def'],
            #    ------------------------------------------------------------------------------------------
        }
        self.assert_sequence(
            manager=manager,
            operations_sequence=OPERATIONS_SEQUENCE,
            expected_stats_sequence=expected_stats_sequence
        )

    def test_sequence_export_interval(self):
        """
        Tests sequence + export_interval
        """
        manager = CollectorTestManager({
            'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='A', export_interval=1),
                periodicstats.Observer(key='B', export_interval=2),
                periodicstats.Observer(key='C', export_interval=3),
                periodicstats.Observer(key='D', export_interval=4),
                periodicstats.Observer(key='E', export_interval=5),
                periodicstats.Observer(key='F', export_interval=6),
            ]
        })
        expected_stats_sequence = {
            #    ------------------------------------------------------------------------------------------
            #        1        2        3        4        5        6        7        8        9       10
            #    ------------------------------------------------------------------------------------------
            "A": [  None ,     10 ,     13 ,     13 ,     18 ,     28 ,     32 ,     32 ,     32 ,     40 ],
            "B": [     5 ,   None ,     20 ,   None ,     10 ,   None ,      0 ,   None ,     60 ,    110 ],
            "C": [  None ,   None ,   None ,      3 ,   None ,   None ,      3 ,   None ,   None ,      6 ],
            "D": [  None ,   None ,   None ,   None ,   True ,   None ,   None ,   None ,  False ,   True ],
            "E": ['black',   None ,   None ,   None ,   None , 'white',   None ,   None ,   None , 'white'],
            "F": [  None ,   None ,   None ,   None ,   None ,   None ,   'def',   None ,   None ,   'def'],
            #    ------------------------------------------------------------------------------------------
        }
        self.assert_sequence(
            manager=manager,
            operations_sequence=OPERATIONS_SEQUENCE,
            expected_stats_sequence=expected_stats_sequence
        )

    def test_sequence_export_interval_only_export_on_change(self):
        """
        Tests sequence + export_interval + only_export_on_change
        """
        manager = CollectorTestManager({
            'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='A', export_interval=1, only_export_on_change=True),
                periodicstats.Observer(key='B', export_interval=2, only_export_on_change=True),
                periodicstats.Observer(key='C', export_interval=3, only_export_on_change=True),
                periodicstats.Observer(key='D', export_interval=4, only_export_on_change=True),
                periodicstats.Observer(key='E', export_interval=5, only_export_on_change=True),
                periodicstats.Observer(key='F', export_interval=6, only_export_on_change=True),
            ]
        })
        expected_stats_sequence = {
            #    ------------------------------------------------------------------------------------------
            #        1        2        3        4        5        6        7        8        9       10
            #    ------------------------------------------------------------------------------------------
            "A": [  None ,     10 ,     13 ,   None ,     18 ,     28 ,     32 ,   None ,   None ,     40 ],
            "B": [     5 ,   None ,     20 ,   None ,     10 ,   None ,      0 ,   None ,     60 ,    110 ],
            "C": [  None ,   None ,   None ,      3 ,   None ,   None ,   None ,   None ,   None ,      6 ],
            "D": [  None ,   None ,   None ,   None ,   True ,   None ,   None ,   None ,  False ,   True ],
            "E": ['black',   None ,   None ,   None ,   None , 'white',   None ,   None ,   None , 'white'],
            "F": [  None ,   None ,   None ,   None ,   None ,   None ,   'def',   None ,   None ,   'def'],
            #    ------------------------------------------------------------------------------------------
        }
        self.assert_sequence(
            manager=manager,
            operations_sequence=OPERATIONS_SEQUENCE,
            expected_stats_sequence=expected_stats_sequence
        )

    def test_sequence_same_key(self):
        """
        Tests sequence with several observers for same key
        """
        manager = CollectorTestManager({
            'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='A', export_key='A1'),
                periodicstats.Observer(key='A', export_key='A2'),
                periodicstats.Observer(key='A', export_key='A3', use_partial_values=True),
                periodicstats.Observer(key='A', export_key='A4', only_export_on_change=True),
                periodicstats.Observer(key='A', export_key='A5', only_export_on_close=True),
                periodicstats.Observer(key='A', export_key='A6', export_interval=3),
                periodicstats.Observer(key='A', export_key='A7', export_interval=3, only_export_on_change=True),
            ]
        })
        expected_stats_sequence = {
            #     ------------------------------------------------------------------------------------------
            #         1        2        3        4        5        6        7        8        9       10
            #     ------------------------------------------------------------------------------------------
            "A1": [  None ,     10 ,     13 ,     13 ,     18 ,     28 ,     32 ,     32 ,     32 ,     40 ],
            "A2": [  None ,     10 ,     13 ,     13 ,     18 ,     28 ,     32 ,     32 ,     32 ,     40 ],
            "A3": [  None ,     10 ,      3 ,      0 ,      5 ,     10 ,      4 ,      0 ,     0 ,       8 ],
            "A4": [  None ,     10 ,     13 ,   None ,     18 ,     28 ,     32 ,   None ,   None ,     40 ],
            "A5": [  None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,     40 ],
            "A6": [  None ,   None ,   None ,     13 ,   None ,   None ,     32 ,   None ,   None ,     40 ],
            "A7": [  None ,   None ,   None ,     13 ,   None ,   None ,     32 ,   None ,   None ,     40 ],
            #     -----------------------------------------------------------------------------------------
        }
        self.assert_sequence(
            manager=manager,
            operations_sequence=OPERATIONS_SEQUENCE,
            expected_stats_sequence=expected_stats_sequence
        )

    def test_sequence_regex(self):
        """
        Tests sequence with regular expression keys
        """
        manager = CollectorTestManager({
            'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='[A-C]', use_re_key=True, export_key='ABC'),
                periodicstats.Observer(key='[A-B]', use_re_key=True, export_key='AB'),
                periodicstats.Observer(key='[A-B]', use_re_key=True, export_key='AB2', export_interval=3),
                periodicstats.Observer(key='[AC]',  use_re_key=True, export_key='AC'),
                periodicstats.Observer(key='[AC]',  use_re_key=True, export_key='AC2', only_export_on_change=True),
                periodicstats.Observer(key='[B-C]', use_re_key=True, export_key='BC'),
                periodicstats.Observer(key='[B-C]', use_re_key=True, export_key='BC2', only_export_on_close=True),
            ]
        })
        expected_stats_sequence = {
            #      ------------------------------------------------------------------------------------------
            #          1        2        3        4        5        6        7        8        9       10
            #      ------------------------------------------------------------------------------------------
            "ABC": [     5 ,     21 ,     36 ,     46 ,     32 ,     21 ,     35 ,     46 ,     98 ,    156 ],
            "AB":  [     5 ,     20 ,     33 ,     43 ,     28 ,     18 ,     32 ,     42 ,     92 ,    150 ],
            "AB2": [     5 ,   None ,   None ,     43 ,   None ,   None ,     32 ,   None ,   None ,    150 ],
            "AC":  [  None ,     11 ,     16 ,     16 ,     22 ,     31 ,     35 ,     36 ,     38 ,     46 ],
            "AC2": [  None ,     11 ,     16 ,   None ,     22 ,     31 ,     35 ,     36 ,     38 ,     46 ],
            "BC":  [     5 ,     11 ,     23 ,     33 ,     14 ,     -7 ,      3 ,     14 ,     66 ,    116 ],
            "BC2": [  None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,   None ,    116 ],
            #      ------------------------------------------------------------------------------------------
        }
        self.assert_sequence(
            manager=manager,
            operations_sequence=OPERATIONS_SEQUENCE,
            expected_stats_sequence=expected_stats_sequence
        )

    def test_config_errors(self):
        """
        Tests configuration errors
        """
        def bad_config_not_an_observer():
            CollectorTestManager({'PERIODIC_STATS_OBSERVERS': [
                'Not an observer'
            ]})

        def bad_config_duplicate_key():
            CollectorTestManager({'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='A'),
                periodicstats.Observer(key='A'),
            ]})

        def bad_config_not_string_pipeline():
            CollectorTestManager({'PERIODIC_STATS_PIPELINES': [
                69
            ]})

        def bad_config_bad_pipeline():
            CollectorTestManager({'PERIODIC_STATS_PIPELINES': [
                'tests.test_periodicstats.CollectorTestManager'
            ]})

        self.assertRaises(NotConfigured, bad_config_not_an_observer)
        self.assertRaises(NotConfigured, bad_config_duplicate_key)
        self.assertRaises(NotConfigured, bad_config_not_string_pipeline)
        self.assertRaises(NotConfigured, bad_config_bad_pipeline)

    def _test_config_disabled(self):
        """
        Tests PERIODIC_STATS_ENABLED parameter
        """
        manager = CollectorTestManager({'PERIODIC_STATS_ENABLED': False})
        manager.collector.inc_value('test', 1)
        self.assertEqual(manager.collector.get_stats(), {'test': 1})
        self.assertEqual(manager.run_interval(), {})

    def test_sequence_config_export_all(self):
        """
        Tests PERIODIC_STATS_EXPORT_ALL parameter
        """
        manager = CollectorTestManager({
            'PERIODIC_STATS_EXPORT_ALL': True,
            'PERIODIC_STATS_EXPORT_ALL_INTERVAL': 1,
            'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='A'),
            ]

        })
        expected_stats_sequence = {
            #    ------------------------------------------------------------------------------------------
            #        1        2        3        4        5        6        7        8        9       10
            #    ------------------------------------------------------------------------------------------
            "A": [  None ,     10 ,     13 ,     13 ,     18 ,     28 ,     32 ,     32 ,     32 ,     40 ],
            "B": [     5 ,     10 ,     20 ,     30 ,     10 ,    -10 ,      0 ,     10 ,     60 ,    110 ],
            "C": [  None ,      1 ,      3 ,      3 ,      4 ,      3 ,      3 ,      4 ,      6 ,      6 ],
            "D": [  None ,   True ,  False ,   True ,   True ,   True ,  False ,  False ,  False ,   True ],
            "E": ['black', 'white', 'black', 'white', 'white', 'white', 'white', 'white', 'black', 'white'],
            "F": [  None ,   None ,   'abc',  'abc' ,   'def',   'def',   'def',   'def',   'def',   'def'],
            #    ------------------------------------------------------------------------------------------
        }
        self.assert_sequence(
            manager=manager,
            operations_sequence=OPERATIONS_SEQUENCE,
            expected_stats_sequence=expected_stats_sequence
        )

    def test_sequence_config_export_all_interval(self):
        """
        Tests PERIODIC_STATS_EXPORT_ALL_INTERVAL parameter
        """
        manager = CollectorTestManager({
            'PERIODIC_STATS_EXPORT_ALL': True,
            'PERIODIC_STATS_EXPORT_ALL_INTERVAL': 4,
            'PERIODIC_STATS_OBSERVERS': [
                periodicstats.Observer(key='A'),
                periodicstats.Observer(key='B', export_interval=2),
            ]
        })
        expected_stats_sequence = {
            #    ------------------------------------------------------------------------------------------
            #        1        2        3        4        5        6        7        8        9       10
            #    ------------------------------------------------------------------------------------------
            "A": [  None ,     10 ,     13 ,     13 ,     18 ,     28 ,     32 ,     32 ,     32 ,     40 ],
            "B": [     5 ,   None ,     20 ,   None ,     10 ,   None ,      0 ,   None ,     60 ,    110 ],
            "C": [  None ,   None ,   None ,   None ,      4 ,   None ,   None ,   None ,      6 ,      6 ],
            "D": [  None ,   None ,   None ,   None ,   True ,   None ,   None ,   None ,  False ,   True ],
            "E": ['black',   None ,   None ,   None , 'white',   None ,   None ,   None , 'black', 'white'],
            "F": [  None ,   None ,   None ,   None ,   'def',   None ,   None ,   None ,   'def',   'def'],
            #    ------------------------------------------------------------------------------------------
        }
        self.assert_sequence(
            manager=manager,
            operations_sequence=OPERATIONS_SEQUENCE,
            expected_stats_sequence=expected_stats_sequence
        )

if __name__ == "__main__":
    unittest.main()


