import unittest

from scrapy import log
from scrapy.conf import settings

class ItemTest(unittest.TestCase):

    def test_get_log_level(self):
        default_log_level = getattr(log, settings['LOG_LEVEL'])
        self.assertEqual(log._get_log_level(), default_log_level)
        self.assertEqual(log._get_log_level('WARNING'), log.WARNING)
        self.assertEqual(log._get_log_level(log.WARNING), log.WARNING)
        self.assertRaises(ValueError, log._get_log_level, 99999)
        self.assertRaises(ValueError, log._get_log_level, object())

if __name__ == "__main__":
    unittest.main()
