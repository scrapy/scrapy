"""
This module is kept to provide a helpful warning about its removal.
"""

import logging
import warnings

from twisted.python.failure import Failure

from scrapy.exceptions import ScrapyDeprecationWarning

logger = logging.getLogger(__name__)

warnings.warn("Module `scrapy.log` has been deprecated, Scrapy now relies on "
              "the builtin Python library for logging. Read the updated "
              "logging entry in the documentation to learn more.",
              ScrapyDeprecationWarning, stacklevel=2)


# Imports kept for backwards-compatibility

DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL
SILENT = CRITICAL + 1


def msg(message, _level=logging.INFO, **kw):
    warnings.warn('log.msg has been deprecated, create a python logger and '
                  'log through it instead',
                  ScrapyDeprecationWarning, stacklevel=2)

    level = kw.pop('level', _level)
    logger.log(level, message, kw)


def err(_stuff=None, _why=None, **kw):
    warnings.warn('log.err has been deprecated, create a python logger and '
                  'use its error method instead',
                  ScrapyDeprecationWarning, stacklevel=2)

    level = kw.pop('level', logging.ERROR)
    failure = kw.pop('failure', _stuff) or Failure()
    message = kw.pop('why', _why) or failure.value
    logger.log(level, message, kw, extra={'failure': failure})
