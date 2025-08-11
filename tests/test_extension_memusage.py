from __future__ import annotations

from unittest import mock

import pytest
from testfixtures import LogCapture
from twisted.internet import defer

from scrapy.crawler import CrawlerRunner
from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


class TestSpider(Spider):
    name = "memory_test"
    start_urls = ["data:text/html,<html><body>test</body></html>"]

    def parse(self, response):
        yield {"test_data": "memory_test", "url": response.url}


class TestMemoryUsage:
    def test_extension_disabled_when_memusage_disabled(self):
        """Extension raises NotConfigured when MEMUSAGE_ENABLED is False."""
        crawler = get_crawler(TestSpider, {"MEMUSAGE_ENABLED": False})
        with pytest.raises(NotConfigured):
            MemoryUsage.from_crawler(crawler)

    @mock.patch("scrapy.extensions.memusage.import_module")
    def test_extension_disabled_when_resource_unavailable(self, mock_import):
        """Extension raises NotConfigured when resource module is not available."""
        mock_import.side_effect = ImportError("No module named 'resource'")
        crawler = get_crawler(TestSpider, {"MEMUSAGE_ENABLED": True})
        with pytest.raises(NotConfigured):
            MemoryUsage.from_crawler(crawler)

    async def test_memory_warning_produces_log_message(self):
        """Memory warning generates proper log message during crawl."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 50,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
            "LOG_LEVEL": "INFO",
        }

        crawler = get_crawler(TestSpider, settings)

        # Mock memory usage to exceed warning threshold
        with (
            mock.patch.object(
                MemoryUsage, "get_virtual_size", return_value=60 * 1024 * 1024
            ),
            LogCapture() as logs,
        ):
            spider = crawler._create_spider("memory_test")
            await defer.maybeDeferred(crawler.crawl, spider)

            # Check that warning message appears in logs
            log_messages = [record.getMessage() for record in logs.records]
            warning_found = any("Memory usage reached" in msg for msg in log_messages)
            assert warning_found, f"Warning message not found in logs: {log_messages}"

            # Check that warning stats are set
            assert crawler.stats.get_value("memusage/warning_reached") == 1

    async def test_memory_limit_closes_spider_with_correct_reason(self):
        """Exceeding memory limit closes spider with 'memusage_exceeded' reason."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 50,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
            "LOG_LEVEL": "INFO",
        }

        crawler = get_crawler(TestSpider, settings)

        # Mock memory usage to exceed limit
        with (
            mock.patch.object(
                MemoryUsage, "get_virtual_size", return_value=60 * 1024 * 1024
            ),
            LogCapture() as logs,
        ):
            spider = crawler._create_spider("memory_test")
            await defer.maybeDeferred(crawler.crawl, spider)

            # Check finish reason
            finish_reason = crawler.stats.get_value("finish_reason")
            assert finish_reason == "memusage_exceeded", (
                f"Expected 'memusage_exceeded', got '{finish_reason}'"
            )

            # Check that limit reached stat is set
            assert crawler.stats.get_value("memusage/limit_reached") == 1

            # Check log message for memory limit exceeded
            log_messages = [record.getMessage() for record in logs.records]
            limit_msg_found = any(
                "Memory usage exceeded" in msg and "Shutting down" in msg
                for msg in log_messages
            )
            assert limit_msg_found, (
                f"Memory limit exceeded message not found: {log_messages}"
            )

    async def test_memory_limit_exceeded_sends_email_notification(self):
        """Memory limit exceeded triggers email notification when configured."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 50,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
            "MEMUSAGE_NOTIFY_MAIL": ["test@example.com"],
            "MAIL_HOST": "localhost",
            "BOT_NAME": "test_bot",
        }

        crawler = get_crawler(TestSpider, settings)

        # Mock memory usage above limit
        with (
            mock.patch.object(
                MemoryUsage, "get_virtual_size", return_value=60 * 1024 * 1024
            ),
            mock.patch("scrapy.mail.MailSender.send") as mock_send,
        ):
            spider = crawler._create_spider("memory_test")
            await defer.maybeDeferred(crawler.crawl, spider)

            # Verify email was sent
            assert mock_send.called, (
                "Email notification should be sent when memory limit exceeded"
            )

            # Verify email stats
            assert crawler.stats.get_value("memusage/limit_notified") == 1

    async def test_memory_warning_sends_email_notification(self):
        """Memory warning triggers email notification when configured."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 50,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
            "MEMUSAGE_NOTIFY_MAIL": ["test@example.com"],
            "MAIL_HOST": "localhost",
            "BOT_NAME": "test_bot",
        }

        crawler = get_crawler(TestSpider, settings)

        # Mock memory usage above warning but below limit
        with (
            mock.patch.object(
                MemoryUsage, "get_virtual_size", return_value=55 * 1024 * 1024
            ),
            mock.patch("scrapy.mail.MailSender.send") as mock_send,
        ):
            spider = crawler._create_spider("memory_test")
            await defer.maybeDeferred(crawler.crawl, spider)

            # Verify email was sent for warning
            assert mock_send.called, (
                "Email notification should be sent when memory warning reached"
            )

            # Verify warning email stats
            assert crawler.stats.get_value("memusage/warning_notified") == 1

    async def test_normal_memory_usage_completes_successfully(self):
        """Crawls complete normally when under memory limits."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 100,
            "MEMUSAGE_LIMIT_MB": 150,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
            "LOG_LEVEL": "INFO",
        }

        crawler = get_crawler(TestSpider, settings)

        # Mock normal memory usage (below thresholds)
        with mock.patch.object(
            MemoryUsage, "get_virtual_size", return_value=30 * 1024 * 1024
        ):
            spider = crawler._create_spider("memory_test")
            await defer.maybeDeferred(crawler.crawl, spider)

            # Verify spider completes with 'finished' reason
            finish_reason = crawler.stats.get_value("finish_reason")
            assert finish_reason == "finished", (
                f"Expected 'finished', got '{finish_reason}'"
            )

            # Verify no warning/limit stats are set
            assert crawler.stats.get_value("memusage/warning_reached") is None
            assert crawler.stats.get_value("memusage/limit_reached") is None

            # Verify max memory usage is tracked
            max_memory = crawler.stats.get_value("memusage/max")
            assert max_memory is not None
            assert max_memory > 0

    async def test_memory_stats_tracking(self):
        """Memory usage statistics are properly tracked."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 100,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
        }

        crawler = get_crawler(TestSpider, settings)

        # Mock increasing memory usage over time
        memory_values = [20 * 1024 * 1024, 40 * 1024 * 1024, 30 * 1024 * 1024]
        with mock.patch.object(
            MemoryUsage, "get_virtual_size", side_effect=memory_values
        ):
            spider = crawler._create_spider("memory_test")
            await defer.maybeDeferred(crawler.crawl, spider)

            # Verify max memory tracks the highest value
            max_memory = crawler.stats.get_value("memusage/max")
            expected_max = max(memory_values)
            assert max_memory >= expected_max, (
                f"Max memory should be at least {expected_max}, got {max_memory}"
            )

    def test_crawler_runner_integration(self):
        """MemoryUsage extension works with CrawlerRunner."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 50,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
        }

        runner = CrawlerRunner(settings)

        # Mock memory usage
        with mock.patch.object(
            MemoryUsage, "get_virtual_size", return_value=40 * 1024 * 1024
        ):
            # Verify runner can be created with MemoryUsage extension
            crawler = runner.create_crawler(TestSpider)
            extension = MemoryUsage.from_crawler(crawler)

            # Verify extension is properly configured
            assert extension.warning == 50 * 1024 * 1024  # 50 MB in bytes
            assert extension.check_interval == 0.1

    async def test_extension_cleanup_on_spider_close(self):
        """MemoryUsage extension cleans up properly when spider closes."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 100,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.5,  # Longer interval for testing
        }

        crawler = get_crawler(TestSpider, settings)

        with mock.patch.object(
            MemoryUsage, "get_virtual_size", return_value=50 * 1024 * 1024
        ):
            spider = crawler._create_spider("memory_test")

            # Get reference to extension
            extension = None
            for ext in crawler.extensions.middlewares:
                if isinstance(ext, MemoryUsage):
                    extension = ext
                    break

            assert extension is not None, "MemoryUsage extension should be loaded"

            # Run crawl
            await defer.maybeDeferred(crawler.crawl, spider)

            # Verify tasks are cleaned up (all should be stopped)
            for task in extension.tasks:
                assert not task.running, (
                    "All tasks should be stopped after spider close"
                )

    def test_configuration_validation(self):
        """MemoryUsage extension validates configuration properly."""
        # Minimal valid configuration
        settings = {"MEMUSAGE_ENABLED": True}
        crawler = get_crawler(TestSpider, settings)
        extension = MemoryUsage.from_crawler(crawler)

        # Verify default values
        assert extension.limit == 0  # Default no limit
        assert extension.warning == 0  # Default no warning
        assert extension.check_interval == 60.0  # Default interval
        assert extension.notify_mails == []  # Default no emails

        # Custom configuration
        custom_settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 200,
            "MEMUSAGE_WARNING_MB": 150,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 30.0,
            "MEMUSAGE_NOTIFY_MAIL": ["admin@example.com", "dev@example.com"],
        }

        crawler = get_crawler(TestSpider, custom_settings)
        extension = MemoryUsage.from_crawler(crawler)

        assert extension.limit == 200 * 1024 * 1024
        assert extension.warning == 150 * 1024 * 1024
        assert extension.check_interval == 30.0
        assert extension.notify_mails == ["admin@example.com", "dev@example.com"]
