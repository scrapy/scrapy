import sys
import unittest


class MyTestCase(unittest.TestCase):
    def test_sys_path_insert(self):
        dirname = '/home/scrapy/fix1/'
        syspath1 = [dirname] + sys.path
        sys.path.insert(0, dirname)
        self.assertEqual(
            syspath1, sys.path
        )
        sys.path.pop(0)
