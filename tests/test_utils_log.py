from __future__ import annotations

import json
import logging
import re
import sys
from io import StringIO
from typing import TYPE_CHECKING, Any

import pytest
from testfixtures import LogCapture
from twisted.python.failure import Failure

from scrapy.utils.log import (
    LogCounterHandler,
    SpiderLoggerAdapter,
    StreamLogger,
    TopLevelFormatter,
    failure_to_exc_info,
)
from scrapy.utils.test import get_crawler
from tests.spiders import LogSpider

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping, MutableMapping

    from scrapy.crawler import Crawler


class TestFailureToExcInfo:
    def test_failure(self):
        try:
            0 / 0
        except ZeroDivisionError:
            exc_info = sys.exc_info()
            failure = Failure()

        assert exc_info == failure_to_exc_info(failure)

    def test_non_failure(self):
        assert failure_to_exc_info("test") is None


class TestTopLevelFormatter:
    def setup_method(self):
        self.handler = LogCapture()
        self.handler.addFilter(TopLevelFormatter(["test"]))

    def test_top_level_logger(self):
        logger = logging.getLogger("test")
        with self.handler as log:
            logger.warning("test log msg")
        log.check(("test", "WARNING", "test log msg"))

    def test_children_logger(self):
        logger = logging.getLogger("test.test1")
        with self.handler as log:
            logger.warning("test log msg")
        log.check(("test", "WARNING", "test log msg"))

    def test_overlapping_name_logger(self):
        logger = logging.getLogger("test2")
        with self.handler as log:
            logger.warning("test log msg")
        log.check(("test2", "WARNING", "test log msg"))

    def test_different_name_logger(self):
        logger = logging.getLogger("different")
        with self.handler as log:
            logger.warning("test log msg")
        log.check(("different", "WARNING", "test log msg"))


class TestLogCounterHandler:
    @pytest.fixture
    def crawler(self) -> Crawler:
        settings = {"LOG_LEVEL": "WARNING"}
        return get_crawler(settings_dict=settings)

    @pytest.fixture
    def logger(self, crawler: Crawler) -> Generator[logging.Logger]:
        logger = logging.getLogger("test")
        logger.setLevel(logging.NOTSET)
        logger.propagate = False
        handler = LogCounterHandler(crawler)
        logger.addHandler(handler)

        yield logger

        logger.propagate = True
        logger.removeHandler(handler)

    def test_init(self, crawler: Crawler, logger: logging.Logger) -> None:
        assert crawler.stats
        assert crawler.stats.get_value("log_count/DEBUG") is None
        assert crawler.stats.get_value("log_count/INFO") is None
        assert crawler.stats.get_value("log_count/WARNING") is None
        assert crawler.stats.get_value("log_count/ERROR") is None
        assert crawler.stats.get_value("log_count/CRITICAL") is None

    def test_accepted_level(self, crawler: Crawler, logger: logging.Logger) -> None:
        logger.error("test log msg")
        assert crawler.stats
        assert crawler.stats.get_value("log_count/ERROR") == 1

    def test_filtered_out_level(self, crawler: Crawler, logger: logging.Logger) -> None:
        logger.debug("test log msg")
        assert crawler.stats
        assert crawler.stats.get_value("log_count/INFO") is None


class TestStreamLogger:
    def test_redirect(self):
        logger = logging.getLogger("test")
        logger.setLevel(logging.WARNING)
        old_stdout = sys.stdout
        sys.stdout = StreamLogger(logger, logging.ERROR)

        with LogCapture() as log:
            print("test log msg")
        log.check(("test", "ERROR", "test log msg"))

        sys.stdout = old_stdout


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
    base_extra: Mapping[str, Any], log_extra: MutableMapping, expected_extra: dict
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
