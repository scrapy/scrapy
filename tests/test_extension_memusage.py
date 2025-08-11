from __future__ import annotations

from typing import TYPE_CHECKING
from unittest import mock

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.mail import MailSender
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


@pytest.fixture
def crawler() -> Crawler:
    """Create a test crawler with MemoryUsage extension enabled."""
    settings = {
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_LIMIT_MB": 100,
        "MEMUSAGE_WARNING_MB": 80,
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 1.0,
        "MEMUSAGE_NOTIFY_MAIL": ["test@example.com"],
        "BOT_NAME": "test_bot",
    }
    return get_crawler(Spider, settings)


@pytest.fixture
def spider(crawler: Crawler) -> Spider:
    """Create a test spider."""
    return crawler._create_spider("test_spider")


class TestMemoryUsage:
    """Test cases for MemoryUsage extension."""

    def test_extension_disabled_when_memusage_disabled(self):
        """Test that extension raises NotConfigured when MEMUSAGE_ENABLED is False."""
        crawler = get_crawler(Spider, {"MEMUSAGE_ENABLED": False})
        with pytest.raises(NotConfigured):
            MemoryUsage.from_crawler(crawler)

    @mock.patch("scrapy.extensions.memusage.import_module")
    def test_extension_disabled_when_resource_unavailable(self, mock_import):
        """Test that extension raises NotConfigured when resource module is not available."""
        mock_import.side_effect = ImportError("No module named 'resource'")
        crawler = get_crawler(Spider, {"MEMUSAGE_ENABLED": True})
        with pytest.raises(NotConfigured):
            MemoryUsage.from_crawler(crawler)

    def test_from_crawler_initialization(self, crawler: Crawler):
        """Test proper initialization from crawler."""
        extension = MemoryUsage.from_crawler(crawler)
        assert extension.crawler is crawler
        assert extension.limit == 100 * 1024 * 1024  # 100 MB in bytes
        assert extension.warning == 80 * 1024 * 1024  # 80 MB in bytes
        assert extension.check_interval == 1.0
        assert extension.notify_mails == ["test@example.com"]
        assert extension.warned is False
        assert isinstance(extension.mail, MailSender)

    @mock.patch("scrapy.extensions.memusage.import_module")
    def test_get_virtual_size_linux(self, mock_import):
        """Test get_virtual_size method on Linux platform."""
        # Mock resource module
        mock_resource = mock.Mock()
        mock_rusage = mock.Mock()
        mock_rusage.ru_maxrss = 1024  # KB on Linux
        mock_resource.getrusage.return_value = mock_rusage
        mock_resource.RUSAGE_SELF = 0
        mock_import.return_value = mock_resource

        crawler = get_crawler(Spider, {"MEMUSAGE_ENABLED": True})

        with mock.patch("sys.platform", "linux"):
            extension = MemoryUsage.from_crawler(crawler)
            size = extension.get_virtual_size()
            assert size == 1024 * 1024  # Should be converted to bytes (KB * 1024)

    @mock.patch("scrapy.extensions.memusage.import_module")
    def test_get_virtual_size_darwin(self, mock_import):
        """Test get_virtual_size method on Darwin (macOS) platform."""
        # Mock resource module
        mock_resource = mock.Mock()
        mock_rusage = mock.Mock()
        mock_rusage.ru_maxrss = 1048576  # Bytes on Darwin
        mock_resource.getrusage.return_value = mock_rusage
        mock_resource.RUSAGE_SELF = 0
        mock_import.return_value = mock_resource

        crawler = get_crawler(Spider, {"MEMUSAGE_ENABLED": True})

        with mock.patch("sys.platform", "darwin"):
            extension = MemoryUsage.from_crawler(crawler)
            size = extension.get_virtual_size()
            assert size == 1048576  # Should remain in bytes on Darwin

    def test_engine_stopped_cleanup(self, crawler: Crawler):
        """Test that engine_stopped properly stops all running tasks."""
        extension = MemoryUsage.from_crawler(crawler)

        # Create mock tasks
        mock_task1 = mock.Mock()
        mock_task1.running = True
        mock_task2 = mock.Mock()
        mock_task2.running = False
        mock_task3 = mock.Mock()
        mock_task3.running = True

        extension.tasks = [mock_task1, mock_task2, mock_task3]

        extension.engine_stopped()

        # Check that running tasks are stopped
        mock_task1.stop.assert_called_once()
        mock_task2.stop.assert_not_called()
        mock_task3.stop.assert_called_once()

    def test_update_method_sets_max_stat(self, crawler: Crawler):
        """Test that update method sets maximum memory usage stat."""
        extension = MemoryUsage.from_crawler(crawler)

        with mock.patch.object(
            extension, "get_virtual_size", return_value=75 * 1024 * 1024
        ):
            extension.update()

        # Should call max_value to track peak memory usage
        expected_memory = 75 * 1024 * 1024
        if crawler.stats:
            assert crawler.stats.get_value("memusage/max") >= expected_memory

    def test_check_warning_below_threshold(self, crawler: Crawler):
        """Test that no warning is triggered when memory is below threshold."""
        extension = MemoryUsage.from_crawler(crawler)

        with mock.patch.object(
            extension, "get_virtual_size", return_value=70 * 1024 * 1024
        ):
            extension._check_warning()

        if crawler.stats:
            assert crawler.stats.get_value("memusage/warning_reached") is None
            assert crawler.stats.get_value("memusage/warning_notified") is None
        assert extension.warned is False
