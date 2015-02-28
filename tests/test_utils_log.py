# -*- coding: utf-8 -*-
import os
import logging
import unittest

from testfixtures import LogCapture
from twisted.python.failure import Failure

from scrapy.utils.log import FailureFormatter


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
                self.logger.exception('test log msg')
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
