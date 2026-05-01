import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.test import get_crawler


@pytest.mark.skipif(
    sys.platform == "win32", reason="resource module not available on Windows"
)
class MemoryUsageExtensionTest(unittest.TestCase):
    def test_extension_disabled_by_default(self):
        crawler = get_crawler(settings_dict={"MEMUSAGE_ENABLED": False})
        with pytest.raises(NotConfigured):
            MemoryUsage(crawler)

    def test_extension_enabled(self):
        crawler = get_crawler(settings_dict={"MEMUSAGE_ENABLED": True})
        ext = MemoryUsage(crawler)
        assert not ext.warned

    @patch("scrapy.extensions.memusage.MemoryUsage.get_virtual_size")
    def test_check_warning_reached(self, mock_get_virtual_size):
        crawler = get_crawler(
            settings_dict={
                "MEMUSAGE_ENABLED": True,
                "MEMUSAGE_WARNING_MB": 10,
            }
        )
        ext = MemoryUsage(crawler)
        crawler.stats = MagicMock()
        crawler.signals = MagicMock()

        mock_get_virtual_size.return_value = 15 * 1024 * 1024

        ext._check_warning()

        crawler.stats.set_value.assert_any_call("memusage/warning_reached", 1)
        assert ext.warned

    @patch("scrapy.extensions.memusage.MemoryUsage.get_virtual_size")
    @patch("scrapy.extensions.memusage._schedule_coro")
    def test_check_limit_reached(self, mock_schedule_coro, mock_get_virtual_size):
        crawler = get_crawler(
            settings_dict={
                "MEMUSAGE_ENABLED": True,
                "MEMUSAGE_LIMIT_MB": 20,
            }
        )
        ext = MemoryUsage(crawler)
        crawler.stats = MagicMock()
        crawler.engine = MagicMock()
        crawler.engine.spider = MagicMock()

        mock_get_virtual_size.return_value = 25 * 1024 * 1024

        ext._check_limit()

        crawler.stats.set_value.assert_any_call("memusage/limit_reached", 1)
        crawler.engine.close_spider_async.assert_called_once_with(
            reason="memusage_exceeded"
        )
