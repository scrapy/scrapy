import unittest

from scrapy.utils.misc import hash_values
from scrapy.core.exceptions import UsageError

class UtilsMiscTestCase(unittest.TestCase):
    def test_hash_values(self):
        self.assertEqual(hash_values('some', 'values', 'to', 'hash'),
                         'f37f5dc65beaaea35af05e16e26d439fd150c576')

        self.assertRaises(UsageError, hash_values, 'some', None, 'value')

if __name__ == "__main__":
    unittest.main()
