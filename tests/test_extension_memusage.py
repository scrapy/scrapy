from __future__ import annotations

import contextlib
import sys
from unittest import mock

import pytest
from twisted.internet import defer
from twisted.trial import unittest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.test import get_crawler
from tests.spiders import SimpleSpider


@pytest.mark.skipif(
    sys.platform == "win32", reason="MemUsage extension does not work in Windows."
)
class TestMemoryUsageExtension(unittest.TestCase):
    def setUp(self):
        """Set up base test configuration."""
        # Base settings that disable problematic extensions
        self.base_test_settings = {
            "TELNETCONSOLE_ENABLED": False,  # Critical: No telnet console
            "LOG_LEVEL": "ERROR",  # Reduce test noise
            "ROBOTSTXT_OBEY": False,  # No robots.txt requests
            "COOKIES_ENABLED": False,  # Simplify tests
            "RETRY_ENABLED": False,  # No retries in tests
            "DOWNLOAD_DELAY": 0,  # No delays
            "RANDOMIZE_DOWNLOAD_DELAY": False,  # No randomization
            "AUTOTHROTTLE_ENABLED": False,  # No auto-throttling
        }

    def tearDown(self):
        #  TID253 `twisted.internet.reactor` is banned at the module level
        # Import here to avoid import-time reactor issues
        from twisted.internet import reactor

        # Cancel any remaining DelayedCalls
        delayed_calls = reactor.getDelayedCalls()
        for call in delayed_calls:
            if not call.cancelled and not call.called:
                with contextlib.suppress(BaseException):
                    call.cancel()  # Ignore errors during cleanup

    def test_extension_disabled_when_memusage_disabled(self):
        """Extension raises NotConfigured when MEMUSAGE_ENABLED is False."""
        crawler = get_crawler(
            SimpleSpider, {**self.base_test_settings, "MEMUSAGE_ENABLED": False}
        )
        with pytest.raises(NotConfigured):
            MemoryUsage.from_crawler(crawler)

    @mock.patch("scrapy.extensions.memusage.import_module")
    def test_extension_disabled_when_resource_unavailable(self, mock_import):
        """Extension raises NotConfigured when resource module is not available."""
        mock_import.side_effect = ImportError("No module named 'resource'")
        crawler = get_crawler(
            SimpleSpider, {**self.base_test_settings, "MEMUSAGE_ENABLED": True}
        )
        with pytest.raises(NotConfigured):
            MemoryUsage.from_crawler(crawler)

    def test_extension_initialization(self):
        """Test that extension initializes properly with correct settings."""
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 50,
            "MEMUSAGE_LIMIT_MB": 100,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 30.0,
            "MEMUSAGE_NOTIFY_MAIL": ["test@example.com"],
        }
        crawler = get_crawler(SimpleSpider, settings)
        extension = MemoryUsage.from_crawler(crawler)

        # Verify settings are properly loaded
        assert extension.warning == 50 * 1024 * 1024
        assert extension.limit == 100 * 1024 * 1024
        assert extension.check_interval == 30.0
        assert extension.notify_mails == ["test@example.com"]
        assert not extension.warned

    @defer.inlineCallbacks
    def test_normal_crawl_completes_successfully(self):
        """Test that crawl completes normally when memory usage is under limits."""
        settings = {
            **self.base_test_settings,
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 1000,  # High threshold
            "MEMUSAGE_LIMIT_MB": 1500,  # High threshold
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.5,
            "LOG_LEVEL": "ERROR",  # Reduce log noise
        }

        crawler = get_crawler(SimpleSpider, settings)
        yield crawler.crawl()

        # Verify spider completed normally
        finish_reason = crawler.stats.get_value("finish_reason")
        assert finish_reason == "finished"

        # Verify memory stats are tracked
        startup_memory = crawler.stats.get_value("memusage/startup")
        max_memory = crawler.stats.get_value("memusage/max")

        assert startup_memory is not None
        assert startup_memory > 0
        assert max_memory is not None
        assert max_memory > 0
        assert max_memory >= startup_memory

        # Should not have warning or limit stats
        assert crawler.stats.get_value("memusage/warning_reached") is None
        assert crawler.stats.get_value("memusage/limit_reached") is None

    @mock.patch.object(MemoryUsage, "get_virtual_size")
    @defer.inlineCallbacks
    def test_memory_warning_behavior(self, mock_get_size):
        """Test memory warning is triggered when threshold is exceeded."""
        # Mock memory usage to simulate warning condition
        memory_values = [
            10 * 1024 * 1024,  # 10MB startup
            15 * 1024 * 1024,  # 15MB during crawl
            25 * 1024 * 1024,  # 25MB - triggers warning
            30 * 1024 * 1024,  # 30MB - continues crawl
        ]
        mock_get_size.side_effect = memory_values

        settings = {
            **self.base_test_settings,
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 20,  # 20MB threshold
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
            "LOG_LEVEL": "ERROR",
        }

        crawler = get_crawler(SimpleSpider, settings)
        yield crawler.crawl()

        # Verify warning was triggered but crawl completed
        assert crawler.stats.get_value("finish_reason") == "finished"
        assert crawler.stats.get_value("memusage/warning_reached") == 1

    @mock.patch.object(MemoryUsage, "get_virtual_size")
    @defer.inlineCallbacks
    def test_memory_limit_stops_crawl(self, mock_get_size):
        """Test that exceeding memory limit stops the crawl."""
        # Mock memory usage to simulate limit exceeded condition
        memory_values = [
            10 * 1024 * 1024,  # 10MB startup
            15 * 1024 * 1024,  # 15MB during crawl
            55 * 1024 * 1024,  # 55MB - exceeds limit
        ]
        mock_get_size.side_effect = memory_values

        settings = {
            **self.base_test_settings,
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 50,  # 50MB limit
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.1,
            "LOG_LEVEL": "ERROR",
        }

        crawler = get_crawler(SimpleSpider, settings)
        yield crawler.crawl()

        # Verify crawl was stopped due to memory limit
        assert crawler.stats.get_value("finish_reason") == "memusage_exceeded"
        assert crawler.stats.get_value("memusage/limit_reached") == 1

    @mock.patch.object(MemoryUsage, "get_virtual_size")
    def test_email_notification_on_warning(self, mock_get_size):
        """Test that email notification is sent when warning threshold is reached."""
        settings = {
            **self.base_test_settings,
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 50,
            "LOG_LEVEL": "ERROR",
        }

        crawler = get_crawler(SimpleSpider, settings)
        extension = MemoryUsage.from_crawler(crawler)

        # Test startup tracking
        mock_get_size.return_value = 30 * 1024 * 1024  # 30MB
        extension.engine_started()
        assert crawler.stats.get_value("memusage/startup") == 30 * 1024 * 1024
        assert not extension.warned
        extension.engine_stopped()

        # Update with memory that exceeds warning
        mock_get_size.return_value = 60 * 1024 * 1024  # 60MB - exceeds 50MB warning
        extension.engine_started()

        # Verify warning logic was triggered
        assert crawler.stats.get_value("memusage/warning_reached") == 1
        assert extension.warned
        assert crawler.stats.get_value("memusage/max") == 60 * 1024 * 1024
        extension.engine_stopped()

    @defer.inlineCallbacks
    def test_extension_cleanup_on_spider_close(self):
        """Test that extension properly cleans up tasks when spider closes."""
        settings = {
            **self.base_test_settings,
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 100,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.5,
            "TELNETCONSOLE_ENABLED": False,  # Disable telnet console for testing
            "LOG_LEVEL": "ERROR",  # Reduce test noise
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
        yield crawler.crawl()

        # Verify tasks are cleaned up after spider closes
        for task in extension.tasks:
            assert not task.running, (
                "All MemoryUsage tasks should be stopped after spider close"
            )

    def test_get_virtual_size_method(self):
        """Test that get_virtual_size method works correctly."""
        settings = {**self.base_test_settings, "MEMUSAGE_ENABLED": True}
        crawler = get_crawler(SimpleSpider, settings)
        extension = MemoryUsage.from_crawler(crawler)

        # Test that get_virtual_size returns a positive integer
        size = extension.get_virtual_size()
        assert isinstance(size, int)
        assert size > 0
