import logging 
from scrapy.utils.log import configure_logging
import unittest
import datetime


class test_log_rotate(unittest.TestCase):
    def setUp(self):
        self.test_settings = {
        "LOG_FILE":"sample.log",
        "LOG_FILE_ROTATE":True,
        "LOG_FILE_ROTATE_WHEN":"midnight",
        "LOG_FILE_ROTATE_INTERVAL":2,
        "LOG_FILE_ROTATE_BACKUP_COUNT":3,
        "LOG_FILE_ROTATE_DELAY":True,
        "LOG_FILE_ROTATE_UTC":True,
        "LOG_FILE_ROTATE_AT_TIME":datetime.time(),       
        }
        configure_logging(settings=self.test_settings)
        self.handler=logging.root.handlers[0]
    
    def test_rotating_handler(self):
        self.assertIsInstance(self.handler,
                              logging.handlers.TimedRotatingFileHandler)
    
    def test_attribute_when(self):
        self.assertEqual(self.handler.when,'midnight'.upper())

    def test_attribute_interval(self):
        self.assertEqual(self.handler.interval,2*24*60*60)

    def test_attribute_backupCount(self):
        self.assertEqual(self.handler.backupCount,3)

    def test_attribute_delay(self):
        self.assertEqual(self.handler.delay,True)

    def test_attribute_utc(self):
        self.assertEqual(self.handler.utc,True)

    def test_attribute_atTime(self):
        self.assertEqual(self.handler.atTime,datetime.time())


if __name__=='__main__':
    unittest.main()


