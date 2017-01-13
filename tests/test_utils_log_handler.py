# from logging import FileHandler
# from logging.handlers import TimedRotatingFileHandler
from scrapy.utils import log
import logging
import unittest


class TestCase(unittest.TestCase):

    def test_settings_None(self):
        log.configure_logging()
        self.assertEqual(logging.getLogger().getEffectiveLevel(), 0)

    def test_settings_LOGGING(self):
        settings = {'LOGGING': {'loggers': {'logger3': {'level': 'CRITICAL'}}}}
        log.configure_logging(settings=settings)
        self.assertEqual(logging.getLogger().getEffectiveLevel(), 30)
        self.assertEqual(logging.getLogger('logger3').getEffectiveLevel(), 50)
