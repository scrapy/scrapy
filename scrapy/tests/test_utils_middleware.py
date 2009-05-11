import unittest

from scrapy.utils.middleware import build_middleware_list

class UtilsMiddlewareTestCase(unittest.TestCase):

    def test_build_middleware_list(self):
        base = {'one': 1, 'two': 2, 'three': 3, 'five': 5, 'six': None}
        custom = {'two': None, 'three': 8, 'four': 4}
        self.assertEqual(build_middleware_list(base, custom),
                         ['one', 'four', 'five', 'three'])

        custom = ['a', 'b', 'c']
        self.assertEqual(build_middleware_list(base, custom), custom)

if __name__ == "__main__":
    unittest.main()
