import unittest
import warnings

from scrapy.exceptions import UsageError, ScrapyDeprecationWarning
from scrapy.settings import BaseSettings, Settings
from scrapy.utils.conf import (
    arglist_to_dict,
    build_component_list,
    feed_complete_default_values_from_settings,
    feed_process_params_from_cli
)


class BuildComponentListTest(unittest.TestCase):

    def test_build_dict(self):
        d = {'one': 1, 'two': None, 'three': 8, 'four': 4}
        self.assertEqual(build_component_list(d, convert=lambda x: x),
                         ['one', 'four', 'three'])

    def test_backward_compatible_build_dict(self):
        base = {'one': 1, 'two': 2, 'three': 3, 'five': 5, 'six': None}
        custom = {'two': None, 'three': 8, 'four': 4}
        self.assertEqual(build_component_list(base, custom,
                                              convert=lambda x: x),
                         ['one', 'four', 'five', 'three'])

    def test_return_list(self):
        custom = ['a', 'b', 'c']
        self.assertEqual(build_component_list(None, custom,
                                              convert=lambda x: x),
                         custom)

    def test_map_dict(self):
        custom = {'one': 1, 'two': 2, 'three': 3}
        self.assertEqual(build_component_list({}, custom,
                                              convert=lambda x: x.upper()),
                         ['ONE', 'TWO', 'THREE'])

    def test_map_list(self):
        custom = ['a', 'b', 'c']
        self.assertEqual(build_component_list(None, custom,
                                              lambda x: x.upper()),
                         ['A', 'B', 'C'])

    def test_duplicate_components_in_dict(self):
        duplicate_dict = {'one': 1, 'two': 2, 'ONE': 4}
        self.assertRaises(ValueError, build_component_list, {}, duplicate_dict,
                          convert=lambda x: x.lower())

    def test_duplicate_components_in_list(self):
        duplicate_list = ['a', 'b', 'a']
        self.assertRaises(ValueError, build_component_list, None,
                          duplicate_list, convert=lambda x: x)

    def test_duplicate_components_in_basesettings(self):
        # Higher priority takes precedence
        duplicate_bs = BaseSettings({'one': 1, 'two': 2}, priority=0)
        duplicate_bs.set('ONE', 4, priority=10)
        self.assertEqual(build_component_list(duplicate_bs,
                                              convert=lambda x: x.lower()),
                         ['two', 'one'])
        duplicate_bs.set('one', duplicate_bs['one'], priority=20)
        self.assertEqual(build_component_list(duplicate_bs,
                                              convert=lambda x: x.lower()),
                         ['one', 'two'])
        # Same priority raises ValueError
        duplicate_bs.set('ONE', duplicate_bs['ONE'], priority=20)
        self.assertRaises(ValueError, build_component_list, duplicate_bs,
                          convert=lambda x: x.lower())

    def test_valid_numbers(self):
        # work well with None and numeric values
        d = {'a': 10, 'b': None, 'c': 15, 'd': 5.0}
        self.assertEqual(build_component_list(d, convert=lambda x: x),
                         ['d', 'a', 'c'])
        d = {'a': 33333333333333333333, 'b': 11111111111111111111, 'c': 22222222222222222222}
        self.assertEqual(build_component_list(d, convert=lambda x: x),
                         ['b', 'c', 'a'])
        # raise exception for invalid values
        d = {'one': '5'}
        self.assertRaises(ValueError, build_component_list, {}, d, convert=lambda x: x)
        d = {'one': '1.0'}
        self.assertRaises(ValueError, build_component_list, {}, d, convert=lambda x: x)
        d = {'one': [1, 2, 3]}
        self.assertRaises(ValueError, build_component_list, {}, d, convert=lambda x: x)
        d = {'one': {'a': 'a', 'b': 2}}
        self.assertRaises(ValueError, build_component_list, {}, d, convert=lambda x: x)
        d = {'one': 'lorem ipsum'}
        self.assertRaises(ValueError, build_component_list, {}, d, convert=lambda x: x)


class UtilsConfTestCase(unittest.TestCase):

    def test_arglist_to_dict(self):
        self.assertEqual(arglist_to_dict(['arg1=val1', 'arg2=val2']),
            {'arg1': 'val1', 'arg2': 'val2'})


class FeedExportConfigTestCase(unittest.TestCase):

    def test_feed_export_config_invalid_format(self):
        settings = Settings()
        self.assertRaises(UsageError, feed_process_params_from_cli, settings, ['items.dat'], 'noformat')

    def test_feed_export_config_mismatch(self):
        settings = Settings()
        self.assertRaises(
            UsageError,
            feed_process_params_from_cli, settings, ['items1.dat', 'items2.dat'], 'noformat'
        )

    def test_feed_export_config_backward_compatible(self):
        with warnings.catch_warnings(record=True) as cw:
            settings = Settings()
            self.assertEqual(
                {'items.dat': {'format': 'csv'}},
                feed_process_params_from_cli(settings, ['items.dat'], 'csv')
            )
            self.assertEqual(cw[0].category, ScrapyDeprecationWarning)

    def test_feed_export_config_explicit_formats(self):
        settings = Settings()
        self.assertEqual(
            {'items_1.dat': {'format': 'json'}, 'items_2.dat': {'format': 'xml'}, 'items_3.dat': {'format': 'csv'}},
            feed_process_params_from_cli(settings, ['items_1.dat:json', 'items_2.dat:xml', 'items_3.dat:csv'])
        )

    def test_feed_export_config_implicit_formats(self):
        settings = Settings()
        self.assertEqual(
            {'items_1.json': {'format': 'json'}, 'items_2.xml': {'format': 'xml'}, 'items_3.csv': {'format': 'csv'}},
            feed_process_params_from_cli(settings, ['items_1.json', 'items_2.xml', 'items_3.csv'])
        )

    def test_feed_export_config_stdout(self):
        settings = Settings()
        self.assertEqual(
            {'stdout:': {'format': 'pickle'}},
            feed_process_params_from_cli(settings, ['-:pickle'])
        )

    def test_feed_complete_default_values_from_settings_empty(self):
        feed = {}
        settings = Settings({
            "FEED_EXPORT_ENCODING": "custom encoding",
            "FEED_EXPORT_FIELDS": ["f1", "f2", "f3"],
            "FEED_EXPORT_INDENT": 42,
            "FEED_STORE_EMPTY": True,
            "FEED_URI_PARAMS": (1, 2, 3, 4),
        })
        new_feed = feed_complete_default_values_from_settings(feed, settings)
        self.assertEqual(new_feed, {
            "encoding": "custom encoding",
            "fields": ["f1", "f2", "f3"],
            "indent": 42,
            "store_empty": True,
            "uri_params": (1, 2, 3, 4),
        })

    def test_feed_complete_default_values_from_settings_non_empty(self):
        feed = {
            "encoding": "other encoding",
            "fields": None,
        }
        settings = Settings({
            "FEED_EXPORT_ENCODING": "custom encoding",
            "FEED_EXPORT_FIELDS": ["f1", "f2", "f3"],
            "FEED_EXPORT_INDENT": 42,
            "FEED_STORE_EMPTY": True,
        })
        new_feed = feed_complete_default_values_from_settings(feed, settings)
        self.assertEqual(new_feed, {
            "encoding": "other encoding",
            "fields": None,
            "indent": 42,
            "store_empty": True,
            "uri_params": None,
        })


if __name__ == "__main__":
    unittest.main()
