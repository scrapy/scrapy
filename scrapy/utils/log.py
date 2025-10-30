# scrapy/utils/log.py
import logging
import pprint
import sys
from typing import Any, Optional
from logging.config import dictConfig

# Twisted imports (Scrapy test-suite expects these to be used)
try:
    from twisted.internet import asyncioreactor  # type: ignore
    from twisted.python import log as twisted_log  # type: ignore
    from twisted.python.failure import Failure  # type: ignore
except Exception:
    asyncioreactor = None
    twisted_log = None
    Failure = None

from scrapy.settings import Settings

# Minimal defaults similar to upstream defaults but small and safe
DEFAULT_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "loggers": {
        "filelock": {"level": "ERROR"},
        "hpack": {"level": "ERROR"},
        "scrapy": {"level": "DEBUG"},
        "twisted": {"level": "ERROR"},
    },
}

_scrapy_root_handler: Optional[logging.Handler] = None


def failure_to_exc_info(failure: Any):
    """Extract exc_info from Failure instances or return sys.exc_info()."""
    if Failure is not None and isinstance(failure, Failure):
        # twisted Failure exposes type/value/traceback via attributes
        try:
            return (failure.type, failure.value, failure.getTracebackObject())
        except Exception:
            return (failure.type, failure.value, None)
    return sys.exc_info()


class TopLevelFormatter(logging.Filter):
    """Filter that shortens logger names for configured loggers."""

    def __init__(self, loggers: Optional[list[str]] = None):
        super().__init__()
        self.loggers = loggers or []

    def filter(self, record: logging.LogRecord) -> bool:
        if any(record.name.startswith(logger + ".") for logger in self.loggers):
            record.name = record.name.split(".", 1)[0]
        return True


def _get_handler(settings: Settings) -> logging.Handler:
    """Create and return the handler according to settings."""
    filename = settings.get("LOG_FILE")
    if filename:
        mode = "a" if settings.getbool("LOG_FILE_APPEND") else "w"
        encoding = settings.get("LOG_ENCODING")
        handler = logging.FileHandler(filename, mode=mode, encoding=encoding)
    elif settings.getbool("LOG_ENABLED"):
        handler = logging.StreamHandler()
    else:
        handler = logging.NullHandler()

    fmt = settings.get("LOG_FORMAT", "%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    datefmt = settings.get("LOG_DATEFORMAT")
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    handler.setLevel(settings.get("LOG_LEVEL", logging.INFO))
    if settings.getbool("LOG_SHORT_NAMES"):
        handler.addFilter(TopLevelFormatter(["scrapy"]))
    return handler


def _uninstall_scrapy_root_handler() -> None:
    global _scrapy_root_handler
    if _scrapy_root_handler is not None and _scrapy_root_handler in logging.root.handlers:
        logging.root.removeHandler(_scrapy_root_handler)
    _scrapy_root_handler = None


def install_scrapy_root_handler(settings: Settings) -> None:
    """Install (or skip) a root handler depending on settings.

    Important: do NOT install a NullHandler on the root logger — that would
    swallow user builtin logging (logging.warning/info/etc.). If _get_handler
    returns a NullHandler we skip adding it to root.
    """
    global _scrapy_root_handler  # noqa: PLW0603
    _uninstall_scrapy_root_handler()
    logging.root.setLevel(logging.NOTSET)
    _scrapy_root_handler = _get_handler(settings)

    # If _get_handler returned a NullHandler, skip installing it on root.
    if isinstance(_scrapy_root_handler, logging.NullHandler):
        _scrapy_root_handler = None
        return

    logging.root.addHandler(_scrapy_root_handler)


def get_scrapy_root_handler() -> Optional[logging.Handler]:
    return _scrapy_root_handler


def configure_logging(settings: Optional[Settings] = None, install_root_handler: bool = True) -> None:
    """
    Initialize Scrapy logging.

    - routes warnings through python logging
    - starts twisted logging observer if available
    - applies DEFAULT_LOGGING via dictConfig
    - optionally installs a root handler according to settings
    """
    if not sys.warnoptions:
        logging.captureWarnings(True)

    # Start twisted observer if available (safe-guarded)
    if twisted_log is not None:
        try:
            observer = twisted_log.PythonLoggingObserver("twisted")
            observer.start()
        except Exception:
            pass

    # Apply defaults
    try:
        dictConfig(DEFAULT_LOGGING)
    except Exception:
        # if dictConfig fails, fallback to basicConfig
        logging.basicConfig(level=logging.INFO)

    if settings is None:
        settings = Settings()

    if settings.getbool("LOG_STDOUT"):
        sys.stdout = StreamLogger(logging.getLogger("stdout"))

    if install_root_handler:
        install_scrapy_root_handler(settings)


def log_scrapy_info(settings: Settings) -> None:
    logger = logging.getLogger(__name__)
    logger.info("Scrapy %(version)s started (bot: %(bot)s)", {"version": "local", "bot": settings.get("BOT_NAME")})
    software = settings.getlist("LOG_VERSIONS")
    if not software:
        return
    versions = pprint.pformat({}, sort_dicts=False)
    logger.info(f"Versions:\n{versions}")


def log_reactor_info() -> None:
    try:
        from twisted.internet import reactor

        logger = logging.getLogger(__name__)
        logger.debug("Using reactor: %s.%s", reactor.__module__, reactor.__class__.__name__)
        if asyncioreactor is not None and isinstance(reactor, asyncioreactor.AsyncioSelectorReactor):
            logger.debug("Using asyncio event loop")
    except Exception:
        pass


class StreamLogger:
    """Fake stream that writes to a logger (used when LOG_STDOUT True)."""

    def __init__(self, logger: logging.Logger, log_level: int = logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ""

    def write(self, buf: str) -> None:
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())

    def flush(self) -> None:
        for h in self.logger.handlers:
            try:
                h.flush()
            except Exception:
                pass


class LogCounterHandler(logging.Handler):
    """Record log levels count into a crawler stats (simplified placeholder)."""

    def __init__(self, crawler, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.crawler = crawler

    def emit(self, record: logging.LogRecord) -> None:
        # placeholder: real implementation increments crawler.stats
        try:
            if hasattr(self.crawler, "stats") and self.crawler.stats is not None:
                self.crawler.stats.inc_value(f"log_count/{record.levelname}")
        except Exception:
            pass


def logformatter_adapter(logkws: dict) -> tuple[int, str, Any]:
    """
    Adapter that converts a LogFormatter-like dict to args for logger.log.
    This function name is also used in some internal imports; keep a
    compatible signature for tests.
    """
    level = logkws.get("level", logging.INFO)
    message = logkws.get("msg", "") or ""
    args = logkws.get("args", ())
    return (level, message, args)


class SpiderLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        if isinstance(kwargs.get("extra"), dict):
            kwargs["extra"].update(self.extra)
        else:
            kwargs["extra"] = self.extra
        return msg, kwargs

