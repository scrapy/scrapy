"""Tests for scrapy.extensions.memusage.MemoryUsage"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.test import get_crawler


@pytest.fixture
def memusage_settings():
    """Base settings to enable MemoryUsage extension."""
    return {
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_LIMIT_MB": 0,
        "MEMUSAGE_WARNING_MB": 0,
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 60,
    }


def _get_crawler_with_memusage(settings_dict):
    """Create a crawler with MemoryUsage-compatible settings."""
    return get_crawler(settings_dict=settings_dict)


class TestMemoryUsageInit:
    def test_not_configured_when_disabled(self, memusage_settings):
        memusage_settings["MEMUSAGE_ENABLED"] = False
        crawler = _get_crawler_with_memusage(memusage_settings)
        with pytest.raises(Exception):  # NotConfigured
            MemoryUsage(crawler)

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="resource module not available on Windows",
    )
    def test_init_defaults(self, memusage_settings):
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage(crawler)
        assert ext.warned is False
        assert ext.limit == 0
        assert ext.warning == 0
        assert ext.notify_mails == []

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="resource module not available on Windows",
    )
    def test_init_with_limit(self, memusage_settings):
        memusage_settings["MEMUSAGE_LIMIT_MB"] = 100
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage(crawler)
        assert ext.limit == 100 * 1024 * 1024

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="resource module not available on Windows",
    )
    def test_init_with_warning(self, memusage_settings):
        memusage_settings["MEMUSAGE_WARNING_MB"] = 50
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage(crawler)
        assert ext.warning == 50 * 1024 * 1024

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="resource module not available on Windows",
    )
    def test_from_crawler(self, memusage_settings):
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage.from_crawler(crawler)
        assert isinstance(ext, MemoryUsage)


class TestMemoryUsageGetVirtualSize:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="resource module not available on Windows",
    )
    def test_get_virtual_size_returns_int(self, memusage_settings):
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage(crawler)
        size = ext.get_virtual_size()
        assert isinstance(size, int)
        assert size >= 0

    @pytest.mark.skipif(
        sys.platform not in ("linux",),
        reason="Linux-specific KB to bytes conversion",
    )
    def test_get_virtual_size_linux_multiplies_by_1024(self, memusage_settings):
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage(crawler)
        with patch.object(ext.resource, "getrusage") as mock_rusage:
            mock_rusage.return_value = MagicMock(ru_maxrss=1024)  # 1024 KB
            size = ext.get_virtual_size()
            assert size == 1024 * 1024  # Should be in bytes


class TestMemoryUsageUpdate:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="resource module not available on Windows",
    )
    def test_update_sets_max_stat(self, memusage_settings):
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage(crawler)
        with patch.object(ext, "get_virtual_size", return_value=10_000_000):
            ext.update()
        assert crawler.stats.get_value("memusage/max") == 10_000_000

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="resource module not available on Windows",
    )
    def test_update_tracks_maximum(self, memusage_settings):
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage(crawler)
        with patch.object(ext, "get_virtual_size", return_value=10_000_000):
            ext.update()
        with patch.object(ext, "get_virtual_size", return_value=5_000_000):
            ext.update()
        assert crawler.stats.get_value("memusage/max") == 10_000_000


class TestMemoryUsageCheckWarning:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="resource module not available on Windows",
    )
    def test_warning_reached(self, memusage_settings):
        memusage_settings["MEMUSAGE_WARNING_MB"] = 1  # 1 MiB warning threshold
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage(crawler)
        # Set virtual size to exceed warning
        with patch.object(ext, "get_virtual_size", return_value=2 * 1024 * 1024):
            ext._check_warning()
        assert crawler.stats.get_value("memusage/warning_reached") == 1
        assert ext.warned is True

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="resource module not available on Windows",
    )
    def test_warning_not_reached(self, memusage_settings):
        memusage_settings["MEMUSAGE_WARNING_MB"] = 1024  # 1 GiB warning threshold
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage(crawler)
        with patch.object(ext, "get_virtual_size", return_value=1024):
            ext._check_warning()
        assert crawler.stats.get_value("memusage/warning_reached") is None
        assert ext.warned is False

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="resource module not available on Windows",
    )
    def test_warning_only_once(self, memusage_settings):
        memusage_settings["MEMUSAGE_WARNING_MB"] = 1
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage(crawler)
        with patch.object(ext, "get_virtual_size", return_value=2 * 1024 * 1024):
            ext._check_warning()
        assert ext.warned is True
        # Second call should not update stats again (but the value stays 1)
        with patch.object(ext, "get_virtual_size", return_value=3 * 1024 * 1024):
            ext._check_warning()
        assert crawler.stats.get_value("memusage/warning_reached") == 1


class TestMemoryUsageCheckLimit:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="resource module not available on Windows",
    )
    def test_limit_exceeded(self, memusage_settings):
        memusage_settings["MEMUSAGE_LIMIT_MB"] = 1  # 1 MiB limit
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage(crawler)
        crawler.engine = MagicMock()
        crawler.engine.spider = None
        with (
            patch.object(ext, "get_virtual_size", return_value=2 * 1024 * 1024),
            patch("scrapy.extensions.memusage._schedule_coro"),
        ):
            ext._check_limit()
        assert crawler.stats.get_value("memusage/limit_reached") == 1

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="resource module not available on Windows",
    )
    def test_limit_not_exceeded(self, memusage_settings):
        memusage_settings["MEMUSAGE_LIMIT_MB"] = 1024  # 1 GiB limit
        crawler = _get_crawler_with_memusage(memusage_settings)
        ext = MemoryUsage(crawler)
        crawler.engine = MagicMock()
        with patch.object(ext, "get_virtual_size", return_value=1024):
            ext._check_limit()
        assert crawler.stats.get_value("memusage/limit_reached") is None
