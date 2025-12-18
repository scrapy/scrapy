from unittest.mock import MagicMock, patch

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.test import get_crawler as _get_crawler


def get_crawler(settings_dict=None):
    return _get_crawler(settings_dict=settings_dict)


class TestMemoryUsage:
    def test_disabled(self):
        crawler = get_crawler({"MEMUSAGE_ENABLED": False})
        with pytest.raises(NotConfigured):
            MemoryUsage(crawler)

    def test_enabled(self):
        crawler = get_crawler({"MEMUSAGE_ENABLED": True})
        # We need to mock import_module because resource might not represent what we want,
        # or we want to ensure it works even if resource module is missing (though it handles it).
        # Actually, let's just assume we are on a platform that supports it or mock it.
        # on Mac, resource module exists.

        with patch("scrapy.extensions.memusage.import_module"):
            m = MemoryUsage(crawler)
            assert m.limit == 0  # Default is 0 (disabled)
            assert m.warning == 0

    def test_settings(self):
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 100,
            "MEMUSAGE_WARNING_MB": 50,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 10.0,
            "MEMUSAGE_NOTIFY_MAIL": ["user@example.com"],
        }
        crawler = get_crawler(settings)
        with patch("scrapy.extensions.memusage.import_module"):
            m = MemoryUsage(crawler)
            assert m.limit == 100 * 1024 * 1024
            assert m.warning == 50 * 1024 * 1024
            assert m.check_interval == 10.0
            assert m.notify_mails == ["user@example.com"]

    def test_get_virtual_size(self):
        crawler = get_crawler({"MEMUSAGE_ENABLED": True})
        with patch("scrapy.extensions.memusage.import_module") as mock_import:
            mock_resource = MagicMock()
            mock_import.return_value = mock_resource
            # Mock getrusage return value
            mock_resource.getrusage.return_value.ru_maxrss = 1000

            m = MemoryUsage(crawler)

            # Simulate different platforms
            with patch("sys.platform", "linux"):
                assert m.get_virtual_size() == 1000 * 1024

            with patch("sys.platform", "darwin"):
                assert m.get_virtual_size() == 1000

    def test_check_limit_triggered(self):
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 10,  # 10 MB
        }
        crawler = get_crawler(settings)
        crawler.engine = MagicMock()
        crawler.stats = MagicMock()
        crawler.stop_async = MagicMock()

        with patch("scrapy.extensions.memusage.import_module"):
            m = MemoryUsage(crawler)

            # Mock get_virtual_size to return 11 MB
            with (
                patch.object(m, "get_virtual_size", return_value=11 * 1024 * 1024),
                patch("scrapy.extensions.memusage._schedule_coro") as mock_schedule,
            ):
                m._check_limit()

                # Logic: if engine.spider is None, calls stop_async
                crawler.engine.spider = None
                m._check_limit()
                assert crawler.stop_async.called or mock_schedule.called

                # If spider is set
                crawler.engine.spider = MagicMock()
                m._check_limit()
                crawler.engine.close_spider_async.assert_called_with(
                    reason="memusage_exceeded"
                )

                # Check stats
                crawler.stats.set_value.assert_called_with("memusage/limit_reached", 1)

    def test_check_warning_triggered(self):
        settings = {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 10,
        }
        crawler = get_crawler(settings)
        crawler.stats = MagicMock()

        with patch("scrapy.extensions.memusage.import_module"):
            m = MemoryUsage(crawler)

            # 11 MB
            with (
                patch.object(m, "get_virtual_size", return_value=11 * 1024 * 1024),
                patch("scrapy.extensions.memusage.logger") as mock_logger,
            ):
                m._check_warning()
                assert crawler.stats.set_value.call_count >= 1
                mock_logger.warning.assert_called()
                assert m.warned is True

                # Check it warns only once
                mock_logger.reset_mock()
                m._check_warning()
                mock_logger.warning.assert_not_called()
