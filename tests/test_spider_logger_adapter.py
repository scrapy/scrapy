import logging
from io import StringIO
from typing import Any, Dict, Mapping, MutableMapping
from unittest import TestCase

import pytest

from scrapy.utils.spider_logger_adapter import SpiderLoggerAdapter
from tests.spiders import LogSpider


@pytest.mark.parametrize(
    ("base_extra", "log_extra", "expected_extra"),
    (
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
    ),
)
def test_spider_logger_adapter_process(
    base_extra: Mapping[str, Any], log_extra: MutableMapping, expected_extra: Dict
):
    logger = logging.getLogger("test")
    spider_logger_adapter = SpiderLoggerAdapter(logger, base_extra)

    log_message = "test_log_message"
    result_message, result_kwargs = spider_logger_adapter.process(
        log_message, log_extra
    )

    assert result_message == log_message
    assert result_kwargs == expected_extra


class LoggingTestCase(TestCase):
    def setUp(self):
        self.log_stream = StringIO()
        handler = logging.StreamHandler(self.log_stream)
        formatter = logging.Formatter("%(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger = logging.getLogger("log")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        self.handler = handler
        self.logger = logger
        self.spider = LogSpider()

    def tearDown(self):
        self.logger.removeHandler(self.handler)

    def test_debug_logging(self):
        log_message = "Foo message"
        self.spider.log_debug(log_message)
        log_contents = self.log_stream.getvalue()
        assert f"DEBUG - {log_message}\n" == log_contents

    def test_info_logging(self):
        log_message = "Bar message"
        self.spider.log_info(log_message)
        log_contents = self.log_stream.getvalue()
        assert f"INFO - {log_message}\n" == log_contents

    def test_warning_logging(self):
        log_message = "Baz message"
        self.spider.log_warning(log_message)
        log_contents = self.log_stream.getvalue()
        assert f"WARNING - {log_message}\n" == log_contents

    def test_error_logging(self):
        log_message = "Foo bar message"
        self.spider.log_error(log_message)
        log_contents = self.log_stream.getvalue()
        assert f"ERROR - {log_message}\n" == log_contents

    def test_critical_logging(self):
        log_message = "Foo bar baz message"
        self.spider.log_critical(log_message)
        log_contents = self.log_stream.getvalue()
        assert f"CRITICAL - {log_message}\n" == log_contents
