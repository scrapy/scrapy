"""
This module is kept to provide a helpful warning about its removal.
"""
import logging
import warnings

from twisted.python.failure import Failure

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.log import failure_to_exc_info

logger = logging.getLogger(__name__)

warnings.warn("Module `scrapy.log` has been deprecated, Scrapy now relies on "
              "the builtin Python library for logging. Read the updated "
              "logging entry in the documentation to learn more.",
              ScrapyDeprecationWarning, stacklevel=2)


# Imports and level_names variable kept for backwards-compatibility

DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL
SILENT = CRITICAL + 1

level_names = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
    SILENT: "SILENT",
}


def msg(message=None, _level=logging.INFO, **kw):
    warnings.warn('log.msg has been deprecated, create a python logger and '
                  'log through it instead',
                  ScrapyDeprecationWarning, stacklevel=2)

    level = kw.pop('level', _level)
    message = kw.pop('format', message)
    # NOTE: logger.log doesn't handle well passing empty dictionaries with format
    # arguments because of some weird use-case:
    # https://hg.python.org/cpython/file/648dcafa7e5f/Lib/logging/__init__.py#l269
    logger.log(level, message, *[kw] if kw else [])


def err(_stuff=None, _why=None, **kw):
    warnings.warn('log.err has been deprecated, create a python logger and '
                  'use its error method instead',
                  ScrapyDeprecationWarning, stacklevel=2)

    level = kw.pop('level', logging.ERROR)
    failure = kw.pop('failure', _stuff) or Failure()
    message = kw.pop('why', _why) or failure.value
    logger.log(level, message, *[kw] if kw else [], exc_info=failure_to_exc_info(failure))
