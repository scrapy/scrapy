import unittest

from scrapy.utils.conf import build_component_list, arglist_to_dict

class UtilsConfTestCase(unittest.TestCase):

    def test_build_component_list(self):
        base = {'one': 1, 'two': 2, 'three': 3, 'five': 5, 'six': None}
        custom = {'two': None, 'three': 8, 'four': 4}
        self.assertEqual(build_component_list(base, custom),
                         ['one', 'four', 'five', 'three'])

        custom = ['a', 'b', 'c']
        self.assertEqual(build_component_list(base, custom), custom)

    def test_arglist_to_dict(self):
        self.assertEqual(arglist_to_dict(['arg1=val1', 'arg2=val2']),
            {'arg1': 'val1', 'arg2': 'val2'})


if __name__ == "__main__":
    unittest.main()
