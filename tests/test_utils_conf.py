import unittest

from scrapy.settings import BaseSettings
from scrapy.utils.conf import build_component_list, arglist_to_dict


class BuildComponentListTest(unittest.TestCase):

    def test_build_dict(self):
        d = {'one': 1, 'two': None, 'three': 8, 'four': 4}
        self.assertEqual(build_component_list(d, convert=lambda x: x),
                         ['one', 'four', 'three'])

    def test_backwards_compatible_build_dict(self):
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


class UtilsConfTestCase(unittest.TestCase):

    def test_arglist_to_dict(self):
        self.assertEqual(arglist_to_dict(['arg1=val1', 'arg2=val2']),
            {'arg1': 'val1', 'arg2': 'val2'})


if __name__ == "__main__":
    unittest.main()
