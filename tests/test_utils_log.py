from __future__ import annotations

import json
import logging
import re
import sys
import warnings
from io import StringIO
from typing import TYPE_CHECKING, Any, cast

import pytest
from twisted.python import log as twisted_log
from twisted.python.failure import Failure

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.settings import Settings
from scrapy.utils.log import (
    LogCounterHandler,
    SpiderLoggerAdapter,
    StreamLogger,
    TopLevelFormatter,
    _uninstall_scrapy_root_handler,
    configure_logging,
    failure_to_exc_info,
    get_scrapy_root_handler,
    install_scrapy_root_handler,
    logformatter_adapter,
)
from scrapy.utils.test import get_crawler
from tests.spiders import LogSpider

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping, MutableMapping

    from scrapy.crawler import Crawler
    from scrapy.logformatter import LogFormatterResult


class TestFailureToExcInfo:
    def test_failure(self):
        try:
            0 / 0
        except ZeroDivisionError:
            exc_info = sys.exc_info()
            failure = Failure()

        assert exc_info == failure_to_exc_info(failure)

    def test_non_failure(self):
        assert failure_to_exc_info("test") is None  # type: ignore[arg-type]


class TestTopLevelFormatter:
    def test_top_level_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.handler.addFilter(TopLevelFormatter(["test"]))
        logger = logging.getLogger("test")
        logger.warning("test log msg")
        assert ("test", logging.WARNING, "test log msg") in caplog.record_tuples

    def test_children_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.handler.addFilter(TopLevelFormatter(["test"]))
        logger = logging.getLogger("test.test1")
        logger.warning("test log msg")
        assert ("test", logging.WARNING, "test log msg") in caplog.record_tuples

    def test_overlapping_name_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.handler.addFilter(TopLevelFormatter(["test"]))
        logger = logging.getLogger("test2")
        logger.warning("test log msg")
        assert ("test2", logging.WARNING, "test log msg") in caplog.record_tuples

    def test_different_name_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.handler.addFilter(TopLevelFormatter(["test"]))
        logger = logging.getLogger("different")
        logger.warning("test log msg")
        assert ("different", logging.WARNING, "test log msg") in caplog.record_tuples


class TestLogCounterHandler:
    @pytest.fixture
    def crawler(self) -> Crawler:
        settings = {"LOG_LEVEL": "WARNING"}
        return get_crawler(settings_dict=settings)

    @pytest.fixture
    def logger(self, crawler: Crawler) -> Generator[logging.Logger]:
        logger = logging.getLogger("test")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        handler = LogCounterHandler(crawler, level=crawler.settings.get("LOG_LEVEL"))
        logger.addHandler(handler)
        try:
            yield logger
        finally:
            logger.propagate = True
            logger.setLevel(logging.NOTSET)
            logger.removeHandler(handler)

    def test_init(self, crawler: Crawler, logger: logging.Logger) -> None:
        assert crawler.stats.get_value("log_count/DEBUG") is None
        assert crawler.stats.get_value("log_count/INFO") is None
        assert crawler.stats.get_value("log_count/WARNING") is None
        assert crawler.stats.get_value("log_count/ERROR") is None
        assert crawler.stats.get_value("log_count/CRITICAL") is None

    def test_accepted_level(self, crawler: Crawler, logger: logging.Logger) -> None:
        logger.error("test log msg")
        assert crawler.stats.get_value("log_count/ERROR") == 1

    def test_filtered_out_level(self, crawler: Crawler, logger: logging.Logger) -> None:
        logger.debug("test log msg")
        assert crawler.stats.get_value("log_count/DEBUG") is None


class TestStreamLogger:
    def test_redirect(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = logging.getLogger("test")
        logger.setLevel(logging.WARNING)
        old_stdout = sys.stdout
        sys.stdout = StreamLogger(logger, logging.ERROR)

        caplog.clear()
        print("test log msg")
        assert caplog.record_tuples == [("test", logging.ERROR, "test log msg")]

        sys.stdout = old_stdout

    def test_flush(self) -> None:
        class FlushCountingHandler(logging.Handler):
            flushes = 0

            def flush(self) -> None:
                self.flushes += 1

        handler = FlushCountingHandler()
        logger = logging.getLogger("test_flush")
        logger.addHandler(handler)
        try:
            StreamLogger(logger).flush()
        finally:
            logger.removeHandler(handler)
        assert handler.flushes == 1


class TestConfigureLogging:
    @pytest.fixture(autouse=True)
    def restore_logging(self) -> Generator[None]:
        root_handlers = logging.root.handlers[:]
        # configure_logging() adds a Twisted log observer without giving any way
        # to remove it afterwards.
        observers = twisted_log.theLogPublisher.observers[:]
        old_stdout = sys.stdout
        old_showwarning = warnings.showwarning
        try:
            yield
        finally:
            warnings.showwarning = old_showwarning
            sys.stdout = old_stdout
            twisted_log.theLogPublisher.observers[:] = observers
            logging.root.handlers[:] = root_handlers
            _uninstall_scrapy_root_handler()

    @staticmethod
    def _warnings_are_captured() -> bool:
        return warnings.showwarning.__module__ == "logging"

    def test_log_stdout(self) -> None:
        configure_logging(settings={"LOG_STDOUT": True}, install_root_handler=False)
        assert isinstance(sys.stdout, StreamLogger)

    def test_captures_warnings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "warnoptions", [])
        logging.captureWarnings(False)
        configure_logging(install_root_handler=False)
        assert self._warnings_are_captured()

    def test_keeps_warnoptions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "warnoptions", ["default"])
        logging.captureWarnings(False)
        configure_logging(install_root_handler=False)
        assert not self._warnings_are_captured()

    def test_reinstall_root_handler_removed_from_root(self) -> None:
        install_scrapy_root_handler(Settings())
        handler = get_scrapy_root_handler()
        assert handler is not None
        # Something else removed the handler from the root logger.
        logging.root.removeHandler(handler)
        install_scrapy_root_handler(Settings())
        assert get_scrapy_root_handler() is not handler


@pytest.mark.parametrize(
    ("base_extra", "log_extra", "expected_extra"),
    [
        (
            {"spider": "test"},
            {"extra": {"log_extra": "info"}},
            {"extra": {"log_extra": "info", "spider": "test"}},
        ),
        (
            {"spider": "test"},
            {"extra": None},
            {"extra": {"spider": "test"}},
        ),
        (
            {"spider": "test"},
            {"extra": {"spider": "test2"}},
            {"extra": {"spider": "test"}},
        ),
    ],
)
def test_spider_logger_adapter_process(
    base_extra: Mapping[str, Any],
    log_extra: MutableMapping[str, Any],
    expected_extra: dict[str, Any],
) -> None:
    logger = logging.getLogger("test")
    spider_logger_adapter = SpiderLoggerAdapter(logger, base_extra)

    log_message = "test_log_message"
    result_message, result_kwargs = spider_logger_adapter.process(
        log_message, log_extra
    )

    assert result_message == log_message
    assert result_kwargs == expected_extra


class TestLogging:
    @pytest.fixture
    def log_stream(self) -> StringIO:
        return StringIO()

    @pytest.fixture
    def spider(self) -> LogSpider:
        return LogSpider()

    @pytest.fixture(autouse=True)
    def logger(self, log_stream: StringIO) -> Generator[logging.Logger]:
        handler = logging.StreamHandler(log_stream)
        logger = logging.getLogger("log_spider")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        yield logger

        logger.removeHandler(handler)

    def test_debug_logging(self, log_stream: StringIO, spider: LogSpider) -> None:
        log_message = "Foo message"
        spider.log_debug(log_message)
        log_contents = log_stream.getvalue()

        assert log_contents == f"{log_message}\n"

    def test_info_logging(self, log_stream: StringIO, spider: LogSpider) -> None:
        log_message = "Bar message"
        spider.log_info(log_message)
        log_contents = log_stream.getvalue()

        assert log_contents == f"{log_message}\n"

    def test_warning_logging(self, log_stream: StringIO, spider: LogSpider) -> None:
        log_message = "Baz message"
        spider.log_warning(log_message)
        log_contents = log_stream.getvalue()

        assert log_contents == f"{log_message}\n"

    def test_error_logging(self, log_stream: StringIO, spider: LogSpider) -> None:
        log_message = "Foo bar message"
        spider.log_error(log_message)
        log_contents = log_stream.getvalue()

        assert log_contents == f"{log_message}\n"

    def test_critical_logging(self, log_stream: StringIO, spider: LogSpider) -> None:
        log_message = "Foo bar baz message"
        spider.log_critical(log_message)
        log_contents = log_stream.getvalue()

        assert log_contents == f"{log_message}\n"


class TestLoggingWithExtra:
    regex_pattern = re.compile(r"^<LogSpider\s'log_spider'\sat\s[^>]+>$")

    @pytest.fixture
    def log_stream(self) -> StringIO:
        return StringIO()

    @pytest.fixture
    def spider(self) -> LogSpider:
        return LogSpider()

    @pytest.fixture(autouse=True)
    def logger(self, log_stream: StringIO) -> Generator[logging.Logger]:
        handler = logging.StreamHandler(log_stream)
        formatter = logging.Formatter(
            '{"levelname": "%(levelname)s", "message": "%(message)s", "spider": "%(spider)s", "important_info": "%(important_info)s"}'
        )
        handler.setFormatter(formatter)
        logger = logging.getLogger("log_spider")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        yield logger

        logger.removeHandler(handler)

    def test_debug_logging(self, log_stream: StringIO, spider: LogSpider) -> None:
        log_message = "Foo message"
        extra = {"important_info": "foo"}
        spider.log_debug(log_message, extra)
        log_contents_str = log_stream.getvalue()
        log_contents = json.loads(log_contents_str)

        assert log_contents["levelname"] == "DEBUG"
        assert log_contents["message"] == log_message
        assert self.regex_pattern.match(log_contents["spider"])
        assert log_contents["important_info"] == extra["important_info"]

    def test_info_logging(self, log_stream: StringIO, spider: LogSpider) -> None:
        log_message = "Bar message"
        extra = {"important_info": "bar"}
        spider.log_info(log_message, extra)
        log_contents_str = log_stream.getvalue()
        log_contents = json.loads(log_contents_str)

        assert log_contents["levelname"] == "INFO"
        assert log_contents["message"] == log_message
        assert self.regex_pattern.match(log_contents["spider"])
        assert log_contents["important_info"] == extra["important_info"]

    def test_warning_logging(self, log_stream: StringIO, spider: LogSpider) -> None:
        log_message = "Baz message"
        extra = {"important_info": "baz"}
        spider.log_warning(log_message, extra)
        log_contents_str = log_stream.getvalue()
        log_contents = json.loads(log_contents_str)

        assert log_contents["levelname"] == "WARNING"
        assert log_contents["message"] == log_message
        assert self.regex_pattern.match(log_contents["spider"])
        assert log_contents["important_info"] == extra["important_info"]

    def test_error_logging(self, log_stream: StringIO, spider: LogSpider) -> None:
        log_message = "Foo bar message"
        extra = {"important_info": "foo bar"}
        spider.log_error(log_message, extra)
        log_contents_str = log_stream.getvalue()
        log_contents = json.loads(log_contents_str)

        assert log_contents["levelname"] == "ERROR"
        assert log_contents["message"] == log_message
        assert self.regex_pattern.match(log_contents["spider"])
        assert log_contents["important_info"] == extra["important_info"]

    def test_critical_logging(self, log_stream: StringIO, spider: LogSpider) -> None:
        log_message = "Foo bar baz message"
        extra = {"important_info": "foo bar baz"}
        spider.log_critical(log_message, extra)
        log_contents_str = log_stream.getvalue()
        log_contents = json.loads(log_contents_str)

        assert log_contents["levelname"] == "CRITICAL"
        assert log_contents["message"] == log_message
        assert self.regex_pattern.match(log_contents["spider"])
        assert log_contents["important_info"] == extra["important_info"]

    def test_overwrite_spider_extra(
        self, log_stream: StringIO, spider: LogSpider
    ) -> None:
        log_message = "Foo message"
        extra = {"important_info": "foo", "spider": "shouldn't change"}
        spider.log_error(log_message, extra)
        log_contents_str = log_stream.getvalue()
        log_contents = json.loads(log_contents_str)

        assert log_contents["levelname"] == "ERROR"
        assert log_contents["message"] == log_message
        assert self.regex_pattern.match(log_contents["spider"])
        assert log_contents["important_info"] == extra["important_info"]


class TestLogformatterAdapter:
    @staticmethod
    def _log(caplog: pytest.LogCaptureFixture, logkws: LogFormatterResult) -> str:
        with caplog.at_level(logging.INFO):
            logging.getLogger(__name__).log(*logformatter_adapter(logkws))
        return caplog.records[-1].getMessage()

    @pytest.mark.parametrize("args", [None, {}, ()])
    def test_empty_args(
        self,
        caplog: pytest.LogCaptureFixture,
        args: dict[str, Any] | tuple[Any, ...] | None,
    ) -> None:
        logkws = cast(
            "LogFormatterResult",
            {"level": logging.INFO, "msg": "90% done", "args": args},
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            assert self._log(caplog, logkws) == "90% done"

    @pytest.mark.parametrize(
        ("msg", "args"),
        [("%(pct)d%% done", {"pct": 90}), ("%d%% done", (90,))],
    )
    def test_args(
        self,
        caplog: pytest.LogCaptureFixture,
        msg: str,
        args: dict[str, Any] | tuple[Any, ...],
    ) -> None:
        logkws: LogFormatterResult = {"level": logging.INFO, "msg": msg, "args": args}
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            assert self._log(caplog, logkws) == "90% done"

    def test_msg_mapping_placeholders_without_args(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        logkws = cast(
            "LogFormatterResult",
            {"level": logging.INFO, "msg": "%(pct)d%% done", "pct": 90},
        )
        with pytest.warns(ScrapyDeprecationWarning, match="no args"):
            assert self._log(caplog, logkws) == "90% done"
