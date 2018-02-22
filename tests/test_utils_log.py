# -*- coding: utf-8 -*-
from __future__ import print_function

import sys
import logging
import unittest
import warnings

from testfixtures import LogCapture

from twisted.python.failure import Failure

from scrapy.utils.log import (
    configure_logging, failure_to_exc_info, TopLevelFormatter,
    LogCounterHandler, StreamLogger)
from scrapy.utils.test import get_crawler


class FailureToExcInfoTest(unittest.TestCase):

    def test_failure(self):
        try:
            0/0
        except ZeroDivisionError:
            exc_info = sys.exc_info()
            failure = Failure()

        self.assertTupleEqual(exc_info, failure_to_exc_info(failure))

    def test_non_failure(self):
        self.assertIsNone(failure_to_exc_info('test'))


class TopLevelFormatterTest(unittest.TestCase):

    def setUp(self):
        self.handler = LogCapture()
        self.handler.addFilter(TopLevelFormatter(['test']))

    def test_top_level_logger(self):
        logger = logging.getLogger('test')
        with self.handler as l:
            logger.warning('test log msg')

        l.check(('test', 'WARNING', 'test log msg'))

    def test_children_logger(self):
        logger = logging.getLogger('test.test1')
        with self.handler as l:
            logger.warning('test log msg')

        l.check(('test', 'WARNING', 'test log msg'))

    def test_overlapping_name_logger(self):
        logger = logging.getLogger('test2')
        with self.handler as l:
            logger.warning('test log msg')

        l.check(('test2', 'WARNING', 'test log msg'))

    def test_different_name_logger(self):
        logger = logging.getLogger('different')
        with self.handler as l:
            logger.warning('test log msg')

        l.check(('different', 'WARNING', 'test log msg'))


class LogCounterHandlerTest(unittest.TestCase):

    def setUp(self):
        self.logger = logging.getLogger('test')
        self.logger.setLevel(logging.NOTSET)
        self.logger.propagate = False
        self.crawler = get_crawler(settings_dict={'LOG_LEVEL': 'WARNING'})
        self.handler = LogCounterHandler(self.crawler)
        self.logger.addHandler(self.handler)

    def tearDown(self):
        self.logger.propagate = True
        self.logger.removeHandler(self.handler)

    def test_init(self):
        self.assertIsNone(self.crawler.stats.get_value('log_count/DEBUG'))
        self.assertIsNone(self.crawler.stats.get_value('log_count/INFO'))
        self.assertIsNone(self.crawler.stats.get_value('log_count/WARNING'))
        self.assertIsNone(self.crawler.stats.get_value('log_count/ERROR'))
        self.assertIsNone(self.crawler.stats.get_value('log_count/CRITICAL'))

    def test_accepted_level(self):
        self.logger.error('test log msg')
        self.assertEqual(self.crawler.stats.get_value('log_count/ERROR'), 1)

    def test_filtered_out_level(self):
        self.logger.debug('test log msg')
        self.assertIsNone(self.crawler.stats.get_value('log_count/INFO'))


class StreamLoggerTest(unittest.TestCase):

    def setUp(self):
        self.stdout = sys.stdout
        logger = logging.getLogger('test')
        logger.setLevel(logging.WARNING)
        sys.stdout = StreamLogger(logger, logging.ERROR)

    def tearDown(self):
        sys.stdout = self.stdout

    def test_redirect(self):
        with LogCapture() as l:
            print('test log msg')
        l.check(('test', 'ERROR', 'test log msg'))


class CustomLogLevelTest(unittest.TestCase):

    def setUp(self):
        _settings = {
            'LOG_CUSTOM_LEVELS': {
                'test_custom_log_level_error': 'ERROR',
                'test_custom_log_level_debug': 'DEBUG',
            },
            'LOG_LEVEL': 'INFO',
        }
        configure_logging(settings=_settings, install_root_handler=True)
        self.logger_error = logging.getLogger('test_custom_log_level_error')
        self.logger_debug = logging.getLogger('test_custom_log_level_debug')
        self.handler = LogCapture(level=logging.DEBUG)

    def tearDown(self):
        self.logger_debug.setLevel(logging.NOTSET)
        self.logger_error.setLevel(logging.NOTSET)
        for handler in logging.root.handlers:
            logging.root.removeHandler(handler)

    def test_custom_log_level(self):
        with self.handler as logc:
            # the DEBUG logger should log both for debug and error
            self.logger_debug.debug('should be captured')
            self.logger_debug.error('should be captured')
            # the ERROR logger should only log the error
            self.logger_error.debug('should not be captured')
            self.logger_error.error('should be captured')
            logc.check(
                ('test_custom_log_level_debug', 'DEBUG', 'should be captured'),
                ('test_custom_log_level_debug', 'ERROR', 'should be captured'),
                ('test_custom_log_level_error', 'ERROR', 'should be captured'),
            )


class CustomLogLevelBadConfigTest(unittest.TestCase):

    def test_custom_log_level_bad_config(self):
        _settings = {
            'LOG_CUSTOM_LEVELS': {
                'test_custom_log_level_error': 'THISISNOTALEVEL'
            }
        }
        with warnings.catch_warnings(record=True) as w:
            configure_logging(settings=_settings, install_root_handler=True)
        msg = str(w[0].message)
        self.assertEqual(
            'Incorrect log level used in LOG_CUSTOM_LEVELS for logger %s',
            msg)
