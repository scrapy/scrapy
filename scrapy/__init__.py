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


def configure_logging(settings=None, install_root_handler=True):
    """
    Initialize logging defaults for Scrapy.

    :param settings: settings used to configure the logging.
    :type settings: scrapy.settings.Settings or None

    :param install_root_handler: whether to install root logging handler.
    :type install_root_handler: bool

    This function does:

    - Route warnings and twisted logging through Python standard logging
    - Assign DEBUG and ERROR level to Scrapy and Twisted loggers, respectively
    - Route stdout to log if LOG_STDOUT setting is True
    - Install a logging handler for the root logger

    When ``settings`` is None, default settings are used.
    """
    logging.captureWarnings(True)  # Route warnings through python logging

    observer = twisted_log.PythonLoggingObserver("twisted")
    observer.start()  # Route Twisted logging through python logging

    settings = settings or Settings()  # Use default settings if not provided

    # Initialize logging configuration for Scrapy
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": "INFO",
                }
            },
            "root": {"handlers": ["console"], "level": "DEBUG" if settings.getbool("LOG_STDOUT") else "INFO"},
        }
    )

    if settings.getbool("LOG_STDOUT"):
        sys.stdout = StreamLogger(logging.getLogger("stdout"))  # Route stdout to log

    if install_root_handler:
        install_scrapy_root_handler(settings)


def install_scrapy_root_handler(settings):
    """
    Install a logging handler for the root logger according to given settings.

    :param settings: settings used to configure the logging.
    :type settings: scrapy.settings.Settings

    """
    global _scrapy_root_handler

    if (
        _scrapy_root_handler is not None
        and _scrapy_root_handler in logging.root.handlers
    ):
        logging.root.removeHandler(_scrapy_root_handler)

    filename = settings.get("LOG_FILE")
    if filename:
        mode = "a" if settings.getbool("LOG_FILE_APPEND") else "w"
        encoding = settings.get("LOG_ENCODING")
        handler = logging.FileHandler(filename, mode=mode, encoding=encoding)
    elif settings.getbool("LOG_STDOUT"):
        handler = logging.StreamHandler()
    else:
        handler = logging.NullHandler()

    if settings.getbool("LOG_SHORT_NAMES"):
        handler.addFilter(TopLevelFormatter(["scrapy"]))

    formatter = logging.Formatter(
        fmt=settings.get("LOG_FORMAT"), datefmt=settings.get("LOG_DATEFORMAT")
    )
    handler.setFormatter(formatter)
    handler.setLevel(settings.get("LOG_LEVEL"))

    logging.root.addHandler(handler)
    _scrapy_root_handler = handler


class StreamLogger:
    """
    Fake file-like stream object that redirects writes to a logger instance.

    Taken from:
        https://www.electricmonk.nl/log/2011/08/14/redirect-stdout-and-stderr-to-a-logger-in-python/
    """

    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ""

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        for h in self.logger.handlers:
            h.flush()


class TopLevelFormatter(logging.Filter):
    """
    Keep only top level loggers's name (direct children from root) from records.

    This filter will replace Scrapy loggers' names with 'scrapy'. This mimics
    the old Scrapy log behaviour and helps shortening long names.

    Since it can't be set for just one logger (it won't propagate for its
    children), it's going to be set in the root handler, with a parametrized
    `loggers` list where it should act.
    """

    def __init__(self, loggers=None):
        super().__init__()
        self.loggers = loggers or []

    def filter(self, record):
        if any(record.name.startswith(logger + ".") for logger in self.loggers):
            record.name = record.name.split(".", 1)[0]
        return True


_default_logging_settings = {
    "LOG_ENABLED": True,
    "LOG_LEVEL": "DEBUG",
    "LOG_STDOUT": False,
    "LOG_FORMAT": "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    "LOG_DATEFORMAT": "%Y-%m-%d %H:%M:%S",
    "LOG_SHORT_NAMES": False,
    "LOG_FILE": None,
    "LOG_FILE_APPEND": False,
    "LOG_ENCODING": "utf-8",
}


def log_scrapy_info(settings: Settings) -> None:
    """
    Log Scrapy version and components versions.

    :param settings: settings used to configure the logging.
    :type settings: scrapy.settings.Settings

    """
    logger.info(
        "Scrapy %(version)s started (bot: %(bot)s)",
        {"version": scrapy.__version__, "bot": settings["BOT_NAME"]},
    )

    versions = [
        f"{name} {version}"
        for name, version in scrapy_components_versions()
        if name != "Scrapy"
    ]
    logger.info("Versions: %(versions)s", {"versions": ", ".join(versions)})


def log_reactor_info() -> None:
    """
    Log reactor information.

    This logs the reactor and, if using AsyncioSelectorReactor, the asyncio
    event loop.

    """
    from twisted.internet import reactor

    logger.debug("Using reactor: %s.%s", reactor.__module__, reactor.__class__.__name__)

    from twisted.internet import asyncioreactor
    if isinstance(reactor, asyncioreactor.AsyncioSelectorReactor):
        logger.debug(
            "Using asyncio event loop: %s.%s",
            reactor._asyncioEventloop.__module__,
            reactor._asyncioEventloop.__class__.__name__,
        )