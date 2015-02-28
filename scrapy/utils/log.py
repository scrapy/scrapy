# -*- coding: utf-8 -*-

import sys
import logging
from logging.config import dictConfig

from twisted.python import log as twisted_log

import scrapy
from scrapy.settings import overridden_settings

logger = logging.getLogger('scrapy')


DEFAULT_LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'loggers': {
        'scrapy': {
            'level': 'DEBUG',
        },
        'twisted': {
            'level': 'ERROR',
        },
    }
}


def configure_logging(settings=None):
    if not sys.warnoptions:
        # Route warnings through python logging
        logging.captureWarnings(True)

    observer = twisted_log.PythonLoggingObserver('twisted')
    observer.start()

    dictConfig(DEFAULT_LOGGING)


def log_scrapy_info(settings):
    logger.info("Scrapy %(version)s started (bot: %(bot)s)",
                {'version': scrapy.__version__, 'bot': settings['BOT_NAME']})

    logger.info("Optional features available: %(features)s",
                {'features': ", ".join(scrapy.optional_features)})

    d = dict(overridden_settings(settings))
    logger.info("Overridden settings: %(settings)r", {'settings': d})
