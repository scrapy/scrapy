from logging import FileHandler
from logging.handlers import TimedRotatingFileHandler
from scrapy.utils import log
import unittest


class TestCase(unittest.TestCase):


    def test_import_handler(self):
        """Test function: _import_handler"""
        name = 'logging.handlers.TimedRotatingFileHandler'
        self.assertEqual(log._import_hander(name), TimedRotatingFileHandler)

    def test_get_handler(self):
        """Test function: _get_handler with LOG_FILE"""
        # First create log file path
        import os
        import tempfile
        file_path = tempfile.mkstemp()[1]
        settings = {'LOG_FILE': file_path, 'LOG_ENCODIUNG': 'utf-8', 'LOG_LEVEL': 'DEBUG'}
        handler = log._get_handler(settings)
        self.assertIsInstance(handler, FileHandler)
        # Adding LOG_HANDLER to settings should update the handler
        settings['LOG_HANDLER'] = 'logging.handlers.TimedRotatingFileHandler'
        handler = log._get_handler(settings)
        self.assertIsInstance(handler, TimedRotatingFileHandler)
        # Remove log file
        os.remove(file_path)
