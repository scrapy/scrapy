import unittest
from datetime import datetime

from scrapy.utils.simpledb import to_sdb_value

class SimpleddbUtilsTest(unittest.TestCase):

    def test_to_sdb_value(self):
        self.assertEqual(to_sdb_value(123), u'0000000000000123')
        self.assertEqual(to_sdb_value(123L), u'0000000000000123')
        self.assertEqual(to_sdb_value(True), u'1')
        self.assertEqual(to_sdb_value(False), u'0')
        self.assertEqual(to_sdb_value(None), u'')
        self.assertEqual(to_sdb_value(datetime(2009, 01, 01, 10, 10, 10)), \
            u'2009-01-01T10:10:10')
        self.assertEqual(to_sdb_value('test'), 'test')
        self.assertEqual(to_sdb_value(u'test'), u'test')
        self.assertRaises(TypeError, to_sdb_value, object())

if __name__ == "__main__":
    unittest.main()
