from __future__ import annotations

import json
import logging
import re
import sys
import tempfile
import os
from io import StringIO
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from testfixtures import LogCapture
from twisted.python.failure import Failure

from scrapy.utils.log import (
    LogCounterHandler,
    SpiderLoggerAdapter,
    StreamLogger,
    TopLevelFormatter,
    failure_to_exc_info,
    configure_logging,
)
from scrapy.settings import Settings
from scrapy.utils.test import get_crawler
from tests.spiders import LogSpider
import unittest

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


# ==============================================================================
# NEW TESTS FOR SYSTEMD LOGGING FEATURE
# ==============================================================================


class TestSystemdLogging:
    """Tests for systemd journal logging feature"""

    @pytest.fixture(autouse=True)
    def reset_logging(self) -> Generator:
        """Reset logging configuration before and after each test"""
        # Remove all handlers from root logger before test
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        original_level = root.level
        for handler in original_handlers:
            root.removeHandler(handler)

        yield

        # Restore original handlers and level after test
        root.setLevel(original_level)
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)

    def test_systemd_disabled_by_default(self) -> None:
        """Test that systemd logging is disabled by default"""
        settings = Settings()
        configure_logging(settings)

        root = logging.getLogger()
        handlers = root.handlers

        # Should have at least one handler (StreamHandler)
        assert len(handlers) > 0

        # Should NOT have JournalHandler
        handler_types = [type(h).__name__ for h in handlers]
        assert "JournalHandler" not in handler_types

        # Should have StreamHandler
        assert "StreamHandler" in handler_types

    def test_systemd_enabled_with_module_available(self) -> None:
        """Test systemd logging when LOG_SYSTEMD=True and systemd module is available"""
        # Create a handler class that properly inherits from logging.Handler
        class MockJournalHandler(logging.Handler):
            instances = []

            def __init__(self):
                super().__init__()
                MockJournalHandler.instances.append(self)

        # Clear previous instances
        MockJournalHandler.instances = []

        # Create mock module
        mock_systemd = MagicMock()
        mock_journal = MagicMock()
        mock_journal.JournalHandler = MockJournalHandler
        mock_systemd.journal = mock_journal

        with patch.dict(
            "sys.modules", {"systemd": mock_systemd, "systemd.journal": mock_journal}
        ):
            settings = Settings(
                {
                    "LOG_ENABLED": True,
                    "LOG_SYSTEMD": True,
                }
            )

            configure_logging(settings)

            # Verify at least one JournalHandler instance was created
            assert len(MockJournalHandler.instances) >= 1

            # Verify a MockJournalHandler was added to the root logger
            root = logging.getLogger()
            mock_handlers = [
                h for h in root.handlers if isinstance(h, MockJournalHandler)
            ]
            assert len(mock_handlers) >= 1

    def test_systemd_enabled_without_module_raises_import_error(self) -> None:
        """Test that enabling LOG_SYSTEMD without systemd-python raises ImportError"""
        # Ensure systemd.journal is not available
        with patch.dict("sys.modules", {"systemd.journal": None}):
            settings = Settings(
                {
                    "LOG_ENABLED": True,
                    "LOG_SYSTEMD": True,
                }
            )

            # Should raise ImportError when trying to import systemd.journal
            with pytest.raises(ImportError):
                configure_logging(settings)

    def test_systemd_disabled_uses_stream_handler(self) -> None:
        """Test that LOG_SYSTEMD=False uses StreamHandler"""
        settings = Settings(
            {
                "LOG_ENABLED": True,
                "LOG_SYSTEMD": False,
            }
        )

        configure_logging(settings)

        root = logging.getLogger()
        handlers = root.handlers

        # Should have StreamHandler
        handler_types = [type(h).__name__ for h in handlers]
        assert "StreamHandler" in handler_types
        assert "JournalHandler" not in handler_types

    def test_systemd_with_log_file_uses_file_handler(self) -> None:
        """Test that LOG_FILE takes precedence over LOG_SYSTEMD"""
        # Create a temporary log file
        fd, log_file = tempfile.mkstemp(suffix=".log")
        os.close(fd)

        try:
            settings = Settings(
                {
                    "LOG_ENABLED": True,
                    "LOG_SYSTEMD": True,
                    "LOG_FILE": log_file,
                }
            )

            configure_logging(settings)

            root = logging.getLogger()
            handlers = root.handlers

            # Should have FileHandler, not JournalHandler
            handler_types = [type(h).__name__ for h in handlers]
            assert "FileHandler" in handler_types
            assert "JournalHandler" not in handler_types
        finally:
            # Clean up
            if os.path.exists(log_file):
                os.remove(log_file)

    def test_systemd_logging_disabled_when_log_disabled(self) -> None:
        """Test that systemd logging is not used when LOG_ENABLED=False"""

        class MockJournalHandler(logging.Handler):
            instances = []

            def __init__(self):
                super().__init__()
                MockJournalHandler.instances.append(self)

        # Clear previous instances
        MockJournalHandler.instances = []

        mock_systemd = MagicMock()
        mock_journal = MagicMock()
        mock_journal.JournalHandler = MockJournalHandler
        mock_systemd.journal = mock_journal

        with patch.dict(
            "sys.modules", {"systemd": mock_systemd, "systemd.journal": mock_journal}
        ):
            settings = Settings(
                {
                    "LOG_ENABLED": False,
                    "LOG_SYSTEMD": True,
                }
            )

            configure_logging(settings)

            # JournalHandler should NOT be instantiated when logging is disabled
            assert len(MockJournalHandler.instances) == 0

    def test_systemd_handler_receives_log_messages(self) -> None:
        """Test that log messages are sent to JournalHandler when enabled"""
        # Create a mock JournalHandler that captures log records
        captured_records = []

        class MockJournalHandler(logging.Handler):
            def __init__(self):
                super().__init__()

            def emit(self, record):
                captured_records.append(record)

        mock_systemd = MagicMock()
        mock_journal = MagicMock()
        mock_journal.JournalHandler = MockJournalHandler
        mock_systemd.journal = mock_journal

        with patch.dict(
            "sys.modules", {"systemd": mock_systemd, "systemd.journal": mock_journal}
        ):
            settings = Settings(
                {
                    "LOG_ENABLED": True,
                    "LOG_SYSTEMD": True,
                    "LOG_LEVEL": "INFO",
                }
            )

            configure_logging(settings)

            # Log a test message
            logger = logging.getLogger("test_logger")
            test_message = "Test systemd log message"
            logger.info(test_message)

            # Verify the message was captured
            assert len(captured_records) >= 1
            # Find the test message in captured records
            test_records = [
                r for r in captured_records if r.getMessage() == test_message
            ]
            assert len(test_records) == 1
            assert test_records[0].levelname == "INFO"

    def test_systemd_respects_log_level(self) -> None:
        """Test that LOG_LEVEL setting is respected with systemd logging"""
        captured_records = []

        class MockJournalHandler(logging.Handler):
            def __init__(self):
                super().__init__()

            def emit(self, record):
                captured_records.append(record)

        mock_systemd = MagicMock()
        mock_journal = MagicMock()
        mock_journal.JournalHandler = MockJournalHandler
        mock_systemd.journal = mock_journal

        with patch.dict(
            "sys.modules", {"systemd": mock_systemd, "systemd.journal": mock_journal}
        ):
            settings = Settings(
                {
                    "LOG_ENABLED": True,
                    "LOG_SYSTEMD": True,
                    "LOG_LEVEL": "WARNING",
                }
            )

            configure_logging(settings)

            logger = logging.getLogger("test_logger")

            # These should be logged
            logger.warning("Warning message")
            logger.error("Error message")

            # This should NOT be logged (below threshold)
            logger.info("Info message")

            # Filter to only our test messages
            warning_records = [
                r for r in captured_records if r.getMessage() == "Warning message"
            ]
            error_records = [
                r for r in captured_records if r.getMessage() == "Error message"
            ]
            info_records = [
                r for r in captured_records if r.getMessage() == "Info message"
            ]

            # Should have warning and error, but not info
            assert len(warning_records) == 1
            assert len(error_records) == 1
            assert len(info_records) == 0

    def test_systemd_import_error_message_is_helpful(self) -> None:
        """Test that ImportError provides helpful guidance when systemd-python is missing"""
        with patch.dict("sys.modules", {"systemd.journal": None}):
            settings = Settings(
                {
                    "LOG_ENABLED": True,
                    "LOG_SYSTEMD": True,
                }
            )

            with pytest.raises(ImportError) as exc_info:
                configure_logging(settings)

            # The error should mention systemd or give installation hint
            error_msg = str(exc_info.value).lower()
            assert "systemd" in error_msg or "journal" in error_msg


class TestSystemdLoggingIntegration:
    """Integration tests for systemd logging with other Scrapy features"""

    @pytest.fixture(autouse=True)
    def reset_logging(self) -> Generator:
        """Reset logging configuration before and after each test"""
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        original_level = root.level
        for handler in original_handlers:
            root.removeHandler(handler)

        yield

        root.setLevel(original_level)
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)

    def test_systemd_with_log_format(self) -> None:
        """Test that LOG_FORMAT is applied to systemd handler"""

        class MockJournalHandler(logging.Handler):
            def __init__(self):
                super().__init__()

        mock_systemd = MagicMock()
        mock_journal = MagicMock()
        mock_journal.JournalHandler = MockJournalHandler
        mock_systemd.journal = mock_journal

        custom_format = "[%(name)s] %(message)s"

        with patch.dict(
            "sys.modules", {"systemd": mock_systemd, "systemd.journal": mock_journal}
        ):
            settings = Settings(
                {
                    "LOG_ENABLED": True,
                    "LOG_SYSTEMD": True,
                    "LOG_FORMAT": custom_format,
                }
            )

            configure_logging(settings)

            # Get the handler and check its formatter
            root = logging.getLogger()
            journal_handlers = [
                h for h in root.handlers if isinstance(h, MockJournalHandler)
            ]
            assert len(journal_handlers) == 1

            handler = journal_handlers[0]
            if handler.formatter:
                assert handler.formatter._fmt == custom_format

    def test_systemd_with_log_dateformat(self) -> None:
        """Test that LOG_DATEFORMAT is applied to systemd handler"""

        class MockJournalHandler(logging.Handler):
            def __init__(self):
                super().__init__()

        mock_systemd = MagicMock()
        mock_journal = MagicMock()
        mock_journal.JournalHandler = MockJournalHandler
        mock_systemd.journal = mock_journal

        custom_date_format = "%Y-%m-%d %H:%M:%S"

        with patch.dict(
            "sys.modules", {"systemd": mock_systemd, "systemd.journal": mock_journal}
        ):
            settings = Settings(
                {
                    "LOG_ENABLED": True,
                    "LOG_SYSTEMD": True,
                    "LOG_DATEFORMAT": custom_date_format,
                }
            )

            configure_logging(settings)

            # Get the handler and check its formatter's date format
            root = logging.getLogger()
            journal_handlers = [
                h for h in root.handlers if isinstance(h, MockJournalHandler)
            ]
            assert len(journal_handlers) == 1

            handler = journal_handlers[0]
            if handler.formatter:
                assert handler.formatter.datefmt == custom_date_format


# Skip all systemd tests if not on Linux or if systemd-python is not available
@pytest.mark.skipif(
    not pytest.importorskip("systemd.journal", reason="systemd-python not available"),
    reason="systemd-python not available",
)
class TestSystemdJournalLogging(unittest.TestCase):
    """Real tests for systemd journal integration"""

    def setUp(self):
        """Clear any existing logging handlers"""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    def tearDown(self):
        """Clean up logging configuration"""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    def test_journal_handler_is_used_when_enabled(self):
        """Verify that JournalHandler is actually instantiated when LOG_SYSTEMD is True"""
        from systemd.journal import JournalHandler

        settings = Settings()
        settings.set("LOG_ENABLED", True)
        settings.set("LOG_SYSTEMD", True)

        configure_logging(settings)

        root_logger = logging.getLogger()
        handlers = root_logger.handlers

        # Check that we actually have a JournalHandler instance
        self.assertTrue(
            any(isinstance(h, JournalHandler) for h in handlers),
            f"Expected JournalHandler in handlers, got: {[type(h) for h in handlers]}",
        )

    def test_stream_handler_used_when_systemd_disabled(self):
        """Verify that StreamHandler is used when LOG_SYSTEMD is False (default)"""
        from systemd.journal import JournalHandler

        settings = Settings()
        settings.set("LOG_ENABLED", True)
        settings.set("LOG_SYSTEMD", False)

        configure_logging(settings)

        root_logger = logging.getLogger()
        handlers = root_logger.handlers

        # Should NOT have JournalHandler
        self.assertFalse(
            any(isinstance(h, JournalHandler) for h in handlers),
            "JournalHandler should not be used when LOG_SYSTEMD is False",
        )

        # Should have StreamHandler
        self.assertTrue(
            any(isinstance(h, logging.StreamHandler) for h in handlers),
            "Expected StreamHandler when LOG_SYSTEMD is False",
        )

    def test_file_handler_takes_precedence_over_journal(self):
        """Verify that LOG_FILE takes precedence over LOG_SYSTEMD"""
        from systemd.journal import JournalHandler
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            log_file = f.name

        try:
            settings = Settings()
            settings.set("LOG_ENABLED", True)
            settings.set("LOG_SYSTEMD", True)
            settings.set("LOG_FILE", log_file)

            configure_logging(settings)

            root_logger = logging.getLogger()
            handlers = root_logger.handlers

            # Should NOT have JournalHandler (file takes precedence)
            self.assertFalse(
                any(isinstance(h, JournalHandler) for h in handlers),
                "JournalHandler should not be used when LOG_FILE is set",
            )

            # Should have FileHandler
            self.assertTrue(
                any(isinstance(h, logging.FileHandler) for h in handlers),
                "Expected FileHandler when LOG_FILE is set",
            )
        finally:
            if os.path.exists(log_file):
                os.unlink(log_file)

    def test_journal_handler_respects_log_level(self):
        """Verify that LOG_LEVEL setting works with systemd logging"""
        from systemd.journal import JournalHandler

        settings = Settings()
        settings.set("LOG_ENABLED", True)
        settings.set("LOG_SYSTEMD", True)
        settings.set("LOG_LEVEL", "WARNING")

        # This should not raise any exceptions
        configure_logging(settings)

        # Verify JournalHandler was created successfully
        root_logger = logging.getLogger()
        journal_handlers = [
            h for h in root_logger.handlers if isinstance(h, JournalHandler)
        ]
        self.assertTrue(
            journal_handlers, "JournalHandler should be present when LOG_LEVEL is set"
        )

    def test_journal_handler_has_formatter(self):
        """Verify that JournalHandler gets a formatter with the configured format"""
        from systemd.journal import JournalHandler

        settings = Settings()
        settings.set("LOG_ENABLED", True)
        settings.set("LOG_SYSTEMD", True)
        custom_format = "%(levelname)s - %(name)s - %(message)s"
        settings.set("LOG_FORMAT", custom_format)

        configure_logging(settings)

        root_logger = logging.getLogger()
        journal_handlers = [
            h for h in root_logger.handlers if isinstance(h, JournalHandler)
        ]

        self.assertTrue(journal_handlers, "No JournalHandler found")

        handler = journal_handlers[0]
        formatter = handler.formatter

        self.assertIsNotNone(formatter, "JournalHandler should have a formatter")
        self.assertEqual(formatter._fmt, custom_format)

    def test_can_actually_send_log_to_journal(self):
        """Test that we can actually send a log message through JournalHandler without errors"""
        from systemd.journal import JournalHandler

        settings = Settings()
        settings.set("LOG_ENABLED", True)
        settings.set("LOG_SYSTEMD", True)

        configure_logging(settings)

        # Get a logger and send a test message
        logger = logging.getLogger("scrapy.test")

        # This should not raise any exceptions
        try:
            logger.info("Test message to systemd journal")
            logger.warning("Test warning to systemd journal")
            logger.error("Test error to systemd journal")
        except Exception as e:
            self.fail(f"Sending logs to journal raised an exception: {e}")

        # Verify the handler is actually a JournalHandler
        root_logger = logging.getLogger()
        self.assertTrue(
            any(isinstance(h, JournalHandler) for h in root_logger.handlers),
            "JournalHandler should be present",
        )

    def test_default_is_not_systemd(self):
        """Verify that default behavior (no LOG_SYSTEMD setting) doesn't use systemd"""
        from systemd.journal import JournalHandler

        settings = Settings()
        settings.set("LOG_ENABLED", True)
        # Don't set LOG_SYSTEMD at all - test default behavior

        configure_logging(settings)

        root_logger = logging.getLogger()
        handlers = root_logger.handlers

        # Should NOT have JournalHandler by default
        self.assertFalse(
            any(isinstance(h, JournalHandler) for h in handlers),
            "JournalHandler should not be used by default (backwards compatibility)",
        )

    def test_log_disabled_prevents_journal_handler(self):
        """Verify that LOG_ENABLED=False prevents JournalHandler even if LOG_SYSTEMD=True"""
        from systemd.journal import JournalHandler

        settings = Settings()
        settings.set("LOG_ENABLED", False)
        settings.set("LOG_SYSTEMD", True)

        configure_logging(settings)

        root_logger = logging.getLogger()

        # Should NOT have JournalHandler when logging is disabled
        self.assertFalse(
            any(isinstance(h, JournalHandler) for h in root_logger.handlers),
            "JournalHandler should not be used when LOG_ENABLED is False",
        )

    def test_multiple_configure_calls_dont_duplicate_handlers(self):
        """Test that calling configure_logging multiple times doesn't create duplicate handlers"""
        from systemd.journal import JournalHandler

        settings = Settings()
        settings.set("LOG_ENABLED", True)
        settings.set("LOG_SYSTEMD", True)

        # Configure twice
        configure_logging(settings)
        initial_count = len(logging.getLogger().handlers)

        configure_logging(settings)
        final_count = len(logging.getLogger().handlers)

        # Handler count should be the same (handlers should be replaced, not duplicated)
        self.assertEqual(
            initial_count,
            final_count,
            f"Handlers were duplicated: initial={initial_count}, final={final_count}",
        )


class TestSystemdImportError(unittest.TestCase):
    """Test error handling when systemd module is not available"""

    def setUp(self):
        """Clear handlers"""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    def tearDown(self):
        """Restore logging handlers"""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    def test_import_error_raised_when_systemd_missing(self):
        """Test that a clear ImportError is raised when systemd-python is not installed"""
        settings = Settings()
        settings.set("LOG_ENABLED", True)
        settings.set("LOG_SYSTEMD", True)

        # Temporarily remove systemd.journal from sys.modules to simulate it not being installed
        import sys

        systemd_journal = sys.modules.get("systemd.journal")
        if systemd_journal:
            del sys.modules["systemd.journal"]

        # Also need to remove parent module
        systemd_module = sys.modules.get("systemd")
        if systemd_module:
            del sys.modules["systemd"]

        try:
            # Mock the import to fail
            import builtins

            real_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if "systemd" in name:
                    raise ImportError(f"No module named '{name}'")
                return real_import(name, *args, **kwargs)

            builtins.__import__ = mock_import

            try:
                with self.assertRaises(ImportError) as context:
                    configure_logging(settings)

                # Verify it's the right error
                self.assertIn("systemd", str(context.exception).lower())
            finally:
                builtins.__import__ = real_import

        finally:
            # Restore modules
            if systemd_journal:
                sys.modules["systemd.journal"] = systemd_journal
            if systemd_module:
                sys.modules["systemd"] = systemd_module

