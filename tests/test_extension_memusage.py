from __future__ import annotations

from unittest import mock

import pytest

from scrapy.crawler import CrawlerRunner
from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.spiders import SimpleSpider


class TestMemoryUsage:
    @classmethod
    def setup_class(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def teardown_class(cls):
        cls.mockserver.__exit__(None, None, None)

    def test_extension_disabled_when_memusage_disabled(self):
        """Extension raises NotConfigured when MEMUSAGE_ENABLED is False."""
        crawler = get_crawler(SimpleSpider, {"MEMUSAGE_ENABLED": False})
        with pytest.raises(NotConfigured):
            MemoryUsage.from_crawler(crawler)

    @mock.patch("scrapy.extensions.memusage.import_module")
    def test_extension_disabled_when_resource_unavailable(self, mock_import):
        """Extension raises NotConfigured when resource module is not available."""
        mock_import.side_effect = ImportError("No module named 'resource'")
        crawler = get_crawler(SimpleSpider, {"MEMUSAGE_ENABLED": True})
        with pytest.raises(NotConfigured):
            MemoryUsage.from_crawler(crawler)

    @deferred_f_from_coro_f
    async def test_normal_crawl_completes_with_finished_reason(self):
        """Test that crawl completes normally when memory usage is under limits."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 100,  # High threshold
            "MEMUSAGE_LIMIT_MB": 150,  # High threshold
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
            "LOG_LEVEL": "INFO",
        }

        crawler = get_crawler(SimpleSpider, settings)
        await maybe_deferred_to_future(crawler.crawl())

        # Verify spider completed normally
        finish_reason = crawler.stats.get_value("finish_reason")
        assert finish_reason == "finished", (
            f"Expected normal completion with 'finished', got '{finish_reason}'"
        )

        # Verify memory stats are tracked
        max_memory = crawler.stats.get_value("memusage/max")
        assert max_memory is not None, "Memory usage should be tracked"
        assert max_memory > 0, "Memory usage should be positive"

        # Should not have warning or limit stats
        assert crawler.stats.get_value("memusage/warning_reached") is None
        assert crawler.stats.get_value("memusage/limit_reached") is None

    @deferred_f_from_coro_f
    async def test_memory_warning_logs_and_completes_crawl(
        self, caplog: pytest.LogCaptureFixture
    ):
        """Test that memory warnings are logged but crawl continues."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 1,  # Very low threshold to trigger warning
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
            "LOG_LEVEL": "INFO",
        }

        crawler = get_crawler(SimpleSpider, settings)
        await maybe_deferred_to_future(crawler.crawl())

        # Check that crawl completed normally despite warning
        assert crawler.stats is not None
        finish_reason = crawler.stats.get_value("finish_reason")
        assert finish_reason == "finished", (
            f"Expected 'finished' even with warning, got '{finish_reason}'"
        )

        # Verify warning was logged
        log_messages = [record.getMessage() for record in caplog.records]
        warning_found = False
        for record in caplog.records:
            message = record.getMessage()
            level = str(record.levelname)
            if "Memory usage reached" in message and (
                "WARNING" in level or "warning" in message.lower()
            ):
                warning_found = True
                break
        assert warning_found, (
            f"Memory warning should be logged. Log messages: {log_messages}"
        )

        # Verify warning stats
        assert crawler.stats.get_value("memusage/warning_reached") == 1

    @deferred_f_from_coro_f
    async def test_memory_limit_closes_spider_with_correct_reason(
        self, caplog: pytest.LogCaptureFixture
    ):
        """Test that exceeding memory limit closes spider with 'memusage_exceeded'."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 1,  # Very low threshold to trigger limit
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
            "LOG_LEVEL": "INFO",
        }

        crawler = get_crawler(SimpleSpider, settings)
        await maybe_deferred_to_future(crawler.crawl())

        # Verify spider was closed due to memory limit
        assert crawler.stats is not None
        finish_reason = crawler.stats.get_value("finish_reason")
        assert finish_reason == "memusage_exceeded", (
            f"Expected 'memusage_exceeded', got '{finish_reason}'"
        )

        # Verify limit reached stats
        assert crawler.stats is not None
        assert crawler.stats.get_value("memusage/limit_reached") == 1

        # Verify appropriate log message
        log_messages = [record.getMessage() for record in caplog.records]
        limit_exceeded_found = any(
            ("Memory usage exceeded" in msg and "Shutting down" in msg)
            for msg in log_messages
        )
        assert limit_exceeded_found, (
            f"Memory limit exceeded message should be logged. Messages: {log_messages}"
        )

    @deferred_f_from_coro_f
    async def test_memory_warning_with_email_notification(
        self, caplog: pytest.LogCaptureFixture
    ):
        """Test that memory warning triggers email when notification is configured."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 1,  # Low threshold
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
            "MEMUSAGE_NOTIFY_MAIL": ["test@example.com"],
            "MAIL_HOST": "localhost",
            "BOT_NAME": "test_bot",
            "LOG_LEVEL": "INFO",
        }

        crawler = get_crawler(SimpleSpider, settings)

        with (
            mock.patch("scrapy.mail.MailSender.send") as mock_send,
        ):
            await maybe_deferred_to_future(crawler.crawl())

            # Verify email notification was attempted
            assert mock_send.called, (
                "Email should be sent when memory warning is reached"
            )

            # Verify notification stats
            assert crawler.stats is not None
            assert crawler.stats.get_value("memusage/warning_notified") == 1

            # Verify warning was logged
            log_messages = [record.getMessage() for record in caplog.records]
            warning_found = any("Memory usage reached" in msg for msg in log_messages)
            assert warning_found, "Memory warning should be logged"

    @deferred_f_from_coro_f
    async def test_memory_limit_with_email_notification(
        self, caplog: pytest.LogCaptureFixture
    ):
        """Test that memory limit triggers email and spider closure."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 1,  # Low threshold
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
            "MEMUSAGE_NOTIFY_MAIL": ["admin@example.com"],
            "MAIL_HOST": "localhost",
            "BOT_NAME": "test_bot",
            "LOG_LEVEL": "INFO",
        }

        crawler = get_crawler(SimpleSpider, settings)

        with (
            mock.patch("scrapy.mail.MailSender.send") as mock_send,
        ):
            await maybe_deferred_to_future(crawler.crawl())

            # Verify spider was closed due to memory limit
            assert crawler.stats is not None
            finish_reason = crawler.stats.get_value("finish_reason")
            assert finish_reason == "memusage_exceeded"

            # Verify email notification was sent
            assert mock_send.called, (
                "Email should be sent when memory limit is exceeded"
            )

            # Verify notification stats
            assert crawler.stats is not None
            assert crawler.stats.get_value("memusage/limit_notified") == 1

            # Verify both warning and limit logs
            log_messages = [record.getMessage() for record in caplog.records]

            limit_msg_found = any(
                "Memory usage exceeded" in msg and "Shutting down" in msg
                for msg in log_messages
            )
            assert limit_msg_found, "Memory limit message should be logged"

    @deferred_f_from_coro_f
    async def test_memory_stats_are_tracked_throughout_crawl(self):
        """Test that memory usage statistics are properly tracked during crawl."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 100,  # High enough to not trigger
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
        }

        crawler = get_crawler(SimpleSpider, settings)

        await maybe_deferred_to_future(crawler.crawl())

        # Verify basic memory stats are present
        startup_memory = crawler.stats.get_value("memusage/startup")
        max_memory = crawler.stats.get_value("memusage/max")

        assert startup_memory is not None, "Startup memory should be recorded"
        assert startup_memory > 0, "Startup memory should be positive"

        assert max_memory is not None, "Max memory should be tracked"
        assert max_memory > 0, "Max memory should be positive"
        assert max_memory >= startup_memory, "Max memory should be >= startup memory"

    @deferred_f_from_coro_f
    async def test_crawler_runner_integration(self):
        """Test that MemoryUsage extension works with CrawlerRunner."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 100,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.5,
        }

        runner = CrawlerRunner(settings)
        crawler = runner.create_crawler(SimpleSpider)

        await maybe_deferred_to_future(crawler.crawl())

        max_memory = crawler.stats.get_value("memusage/max")
        assert max_memory is not None, "MemoryUsage extension should track memory"

        extension = MemoryUsage.from_crawler(crawler)
        assert extension.warning == 100 * 1024 * 1024
        assert extension.check_interval == 0.5

    @deferred_f_from_coro_f
    async def test_extension_cleanup_on_spider_close(self):
        """Test that MemoryUsage extension properly cleans up when spider closes."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 100,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.5,
        }

        crawler = get_crawler(SimpleSpider, settings)

        # Get reference to extension before crawl
        extension = None
        for ext in crawler.extensions.middlewares:
            if isinstance(ext, MemoryUsage):
                extension = ext
                break

        assert extension is not None, "MemoryUsage extension should be loaded"

        # Run the crawl
        await maybe_deferred_to_future(crawler.crawl())

        # Verify tasks are cleaned up after spider closes
        for task in extension.tasks:
            assert not task.running, (
                "All MemoryUsage tasks should be stopped after spider close"
            )
