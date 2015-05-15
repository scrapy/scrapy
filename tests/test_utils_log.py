# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import sys
import logging
import unittest

from testfixtures import LogCapture
from twisted.python.failure import Failure

from scrapy.utils.log import (FailureFormatter, TopLevelFormatter,
                              LogCounterHandler, StreamLogger)
from scrapy.utils.test import get_crawler


class FailureFormatterTest(unittest.TestCase):

    def setUp(self):
        self.logger = logging.getLogger('test')
        self.filter = FailureFormatter()
        self.logger.addFilter(self.filter)

    def tearDown(self):
        self.logger.removeFilter(self.filter)

    def test_failure_format(self):
        with LogCapture() as l:
            try:
                0/0
            except ZeroDivisionError:
                self.logger.error('test log msg', exc_info=True)
                failure = Failure()

            self.logger.error('test log msg', extra={'failure': failure})

        self.assertEqual(len(l.records), 2)
        exc_record, failure_record = l.records
        self.assertTupleEqual(failure_record.exc_info, exc_record.exc_info)

        formatter = logging.Formatter()
        self.assertMultiLineEqual(formatter.format(failure_record),
                                  formatter.format(exc_record))

    def test_non_failure_format(self):
        with LogCapture() as l:
            self.logger.error('test log msg', extra={'failure': 3})

        self.assertEqual(len(l.records), 1)
        self.assertMultiLineEqual(l.records[0].getMessage(),
                                  'test log msg' + os.linesep + '3')


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
