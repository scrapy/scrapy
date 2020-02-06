# -*- coding: utf-8 -*-

import logging
import sys
import warnings
from logging.config import dictConfig

from twisted.python import log as twisted_log
from twisted.python.failure import Failure

import scrapy
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.settings import Settings
from scrapy.utils.versions import scrapy_components_versions


logger = logging.getLogger(__name__)


def failure_to_exc_info(failure):
    """Extract exc_info from Failure instances"""
    if isinstance(failure, Failure):
        return (failure.type, failure.value, failure.getTracebackObject())


class TopLevelFormatter(logging.Filter):
    """Keep only top level loggers's name (direct children from root) from
    records.

    This filter will replace Scrapy loggers' names with 'scrapy'. This mimics
    the old Scrapy log behaviour and helps shortening long names.

    Since it can't be set for just one logger (it won't propagate for its
    children), it's going to be set in the root handler, with a parametrized
    ``loggers`` list where it should act.
    """

    def __init__(self, loggers=None):
        self.loggers = loggers or []

    def filter(self, record):
        if any(record.name.startswith(l + '.') for l in self.loggers):
            record.name = record.name.split('.', 1)[0]
        return True


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


def configure_logging(settings=None, install_root_handler=True):
    """
    Initialize logging defaults for Scrapy.

    :param settings: settings used to create and configure a handler for the
        root logger (default: None).
    :type settings: dict, :class:`~scrapy.settings.Settings` object or ``None``

    :param install_root_handler: whether to install root logging handler
        (default: True)
    :type install_root_handler: bool

    This function does:

    - Route warnings and twisted logging through Python standard logging
    - Assign DEBUG and ERROR level to Scrapy and Twisted loggers respectively
    - Route stdout to log if LOG_STDOUT setting is True

    When ``install_root_handler`` is True (default), this function also
    creates a handler for the root logger according to given settings
    (see :ref:`topics-logging-settings`). You can override default options
    using ``settings`` argument. When ``settings`` is empty or None, defaults
    are used.
    """
    if not sys.warnoptions:
        # Route warnings through python logging
        logging.captureWarnings(True)

    observer = twisted_log.PythonLoggingObserver('twisted')
    observer.start()

    dictConfig(DEFAULT_LOGGING)

    if isinstance(settings, dict) or settings is None:
        settings = Settings(settings)

    if settings.getbool('LOG_STDOUT'):
        sys.stdout = StreamLogger(logging.getLogger('stdout'))

    if install_root_handler:
        install_scrapy_root_handler(settings)


def install_scrapy_root_handler(settings):
    global _scrapy_root_handler

    if (_scrapy_root_handler is not None
            and _scrapy_root_handler in logging.root.handlers):
        logging.root.removeHandler(_scrapy_root_handler)
    logging.root.setLevel(logging.NOTSET)
    _scrapy_root_handler = _get_handler(settings)
    logging.root.addHandler(_scrapy_root_handler)


def get_scrapy_root_handler():
    return _scrapy_root_handler


_scrapy_root_handler = None


def _get_handler(settings):
    """ Return a log handler object according to settings """
    filename = settings.get('LOG_FILE')
    if filename:
        encoding = settings.get('LOG_ENCODING')
        handler = logging.FileHandler(filename, encoding=encoding)
    elif settings.getbool('LOG_ENABLED'):
        handler = logging.StreamHandler()
    else:
        handler = logging.NullHandler()

    formatter = logging.Formatter(
        fmt=settings.get('LOG_FORMAT'),
        datefmt=settings.get('LOG_DATEFORMAT')
    )
    handler.setFormatter(formatter)
    handler.setLevel(settings.get('LOG_LEVEL'))
    if settings.getbool('LOG_SHORT_NAMES'):
        handler.addFilter(TopLevelFormatter(['scrapy']))
    return handler


def log_scrapy_info(settings):
    logger.info("Scrapy %(version)s started (bot: %(bot)s)",
                {'version': scrapy.__version__, 'bot': settings['BOT_NAME']})
    logger.info("Versions: %(versions)s",
                {'versions': ", ".join("%s %s" % (name, version)
                    for name, version in scrapy_components_versions()
                    if name != "Scrapy")})
    from twisted.internet import reactor
    logger.debug("Using reactor: %s.%s", reactor.__module__, reactor.__class__.__name__)


class StreamLogger(object):
    """Fake file-like stream object that redirects writes to a logger instance

    Taken from:
        https://www.electricmonk.nl/log/2011/08/14/redirect-stdout-and-stderr-to-a-logger-in-python/
    """
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        for h in self.logger.handlers:
            h.flush()


class LogCounterHandler(logging.Handler):
    """Record log levels count into a crawler stats"""

    def __init__(self, crawler, *args, **kwargs):
        super(LogCounterHandler, self).__init__(*args, **kwargs)
        self.crawler = crawler

    def emit(self, record):
        sname = 'log_count/{}'.format(record.levelname)
        self.crawler.stats.inc_value(sname)


def logformatter_adapter(logkws):
    """
    Helper that takes the dictionary output from the methods in LogFormatter
    and adapts it into a tuple of positional arguments for logger.log calls,
    handling backward compatibility as well.
    """
    if not {'level', 'msg', 'args'} <= set(logkws):
        warnings.warn('Missing keys in LogFormatter method',
                      ScrapyDeprecationWarning)

    if 'format' in logkws:
        warnings.warn('`format` key in LogFormatter methods has been '
                      'deprecated, use `msg` instead',
                      ScrapyDeprecationWarning)

    level = logkws.get('level', logging.INFO)
    message = logkws.get('format', logkws.get('msg'))
    # NOTE: This also handles 'args' being an empty dict, that case doesn't
    # play well in logger.log calls
    args = logkws if not logkws.get('args') else logkws['args']

    return (level, message, args)
