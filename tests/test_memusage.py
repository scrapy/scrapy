"""Tests for scrapy.extensions.memusage.MemoryUsage"""

from __future__ import annotations

import sys
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test


def _make_crawler(settings_dict=None):
    """Return a configured crawler with MEMUSAGE_ENABLED=True."""
    base = {
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_LIMIT_MB": 0,
        "MEMUSAGE_WARNING_MB": 0,
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 60.0,
        "MEMUSAGE_NOTIFY_MAIL": [],
    }
    if settings_dict:
        base.update(settings_dict)
    return get_crawler(settings_dict=base)


class TestMemoryUsageInit:
    """Tests for MemoryUsage.__init__ / from_crawler."""

    def test_not_configured_when_disabled(self):
        crawler = get_crawler(settings_dict={"MEMUSAGE_ENABLED": False})
        with pytest.raises(NotConfigured):
            MemoryUsage(crawler)

    def test_not_configured_when_resource_unavailable(self):
        """MemoryUsage raises NotConfigured when the resource module is absent."""
        crawler = _make_crawler()
        with patch.dict(sys.modules, {"resource": None}):
            with pytest.raises(NotConfigured):
                MemoryUsage(crawler)

    def test_from_crawler(self):
        crawler = _make_crawler()
        with patch("importlib.import_module", return_value=MagicMock()):
            ext = MemoryUsage.from_crawler(crawler)
        assert ext.crawler is crawler
        assert ext.warned is False


class TestMemoryUsageNormalOperation:
    """Memory is below both warning and limit thresholds — nothing special happens."""

    @coroutine_test
    async def test_normal_operation_no_warning_no_limit(self):
        """When memory is below both thresholds, no stat keys are set."""
        crawler = _make_crawler(
            {
                "MEMUSAGE_WARNING_MB": 100,
                "MEMUSAGE_LIMIT_MB": 200,
                "MEMUSAGE_CHECK_INTERVAL_SECONDS": 60.0,
            }
        )
        # memory usage reported: 50 MiB (below both thresholds)
        low_mem = 50 * 1024 * 1024

        resource_mock = MagicMock()
        resource_mock.getrusage.return_value.ru_maxrss = low_mem
        resource_mock.RUSAGE_SELF = 0

        with patch("importlib.import_module", return_value=resource_mock):
            ext = MemoryUsage.from_crawler(crawler)

        with patch.object(ext, "get_virtual_size", return_value=low_mem):
            # Simulate engine_started signal
            await crawler._apply_settings()
            crawler.stats.open_spider(None)
            ext.engine_started()
            ext._check_warning()
            ext._check_limit()
            ext.engine_stopped()

        assert crawler.stats.get_value("memusage/warning_reached") is None
        assert crawler.stats.get_value("memusage/limit_reached") is None
        assert ext.warned is False


class TestMemoryUsageWarningThreshold:
    """Memory exceeds warning threshold → warning stats and signal are triggered."""

    @coroutine_test
    async def test_warning_stat_set_when_threshold_exceeded(self):
        crawler = _make_crawler(
            {
                "MEMUSAGE_WARNING_MB": 100,
                "MEMUSAGE_LIMIT_MB": 0,  # no limit
                "MEMUSAGE_CHECK_INTERVAL_SECONDS": 60.0,
            }
        )
        high_mem = 150 * 1024 * 1024  # 150 MiB > 100 MiB warning

        resource_mock = MagicMock()
        resource_mock.getrusage.return_value.ru_maxrss = high_mem
        resource_mock.RUSAGE_SELF = 0

        with patch("importlib.import_module", return_value=resource_mock):
            ext = MemoryUsage.from_crawler(crawler)

        with patch.object(ext, "get_virtual_size", return_value=high_mem):
            await crawler._apply_settings()
            crawler.stats.open_spider(None)
            ext.engine_started()
            ext._check_warning()
            ext.engine_stopped()

        assert crawler.stats.get_value("memusage/warning_reached") == 1
        assert ext.warned is True

    @coroutine_test
    async def test_warning_signal_sent(self):
        crawler = _make_crawler(
            {
                "MEMUSAGE_WARNING_MB": 100,
                "MEMUSAGE_LIMIT_MB": 0,
                "MEMUSAGE_CHECK_INTERVAL_SECONDS": 60.0,
            }
        )
        high_mem = 150 * 1024 * 1024

        resource_mock = MagicMock()
        resource_mock.getrusage.return_value.ru_maxrss = high_mem
        resource_mock.RUSAGE_SELF = 0

        with patch("importlib.import_module", return_value=resource_mock):
            ext = MemoryUsage.from_crawler(crawler)

        signal_received = []

        def on_warning():
            signal_received.append(True)

        crawler.signals.connect(on_warning, signal=signals.memusage_warning_reached)

        with patch.object(ext, "get_virtual_size", return_value=high_mem):
            await crawler._apply_settings()
            crawler.stats.open_spider(None)
            ext.engine_started()
            ext._check_warning()
            ext.engine_stopped()

        assert signal_received, "memusage_warning_reached signal was not sent"

    @coroutine_test
    async def test_warning_only_triggered_once(self):
        """_check_warning respects the self.warned flag and warns only once."""
        crawler = _make_crawler(
            {
                "MEMUSAGE_WARNING_MB": 100,
                "MEMUSAGE_LIMIT_MB": 0,
                "MEMUSAGE_CHECK_INTERVAL_SECONDS": 60.0,
            }
        )
        high_mem = 150 * 1024 * 1024

        resource_mock = MagicMock()
        resource_mock.getrusage.return_value.ru_maxrss = high_mem
        resource_mock.RUSAGE_SELF = 0

        with patch("importlib.import_module", return_value=resource_mock):
            ext = MemoryUsage.from_crawler(crawler)

        signal_count = []

        def on_warning():
            signal_count.append(1)

        crawler.signals.connect(on_warning, signal=signals.memusage_warning_reached)

        with patch.object(ext, "get_virtual_size", return_value=high_mem):
            await crawler._apply_settings()
            crawler.stats.open_spider(None)
            ext.engine_started()
            ext._check_warning()
            ext._check_warning()  # second call — should be a no-op
            ext.engine_stopped()

        assert len(signal_count) == 1, "Warning signal should only fire once"

    @coroutine_test
    async def test_no_warning_when_below_threshold(self):
        crawler = _make_crawler(
            {
                "MEMUSAGE_WARNING_MB": 100,
                "MEMUSAGE_LIMIT_MB": 0,
                "MEMUSAGE_CHECK_INTERVAL_SECONDS": 60.0,
            }
        )
        low_mem = 50 * 1024 * 1024  # 50 MiB < 100 MiB warning

        resource_mock = MagicMock()
        resource_mock.getrusage.return_value.ru_maxrss = low_mem
        resource_mock.RUSAGE_SELF = 0

        with patch("importlib.import_module", return_value=resource_mock):
            ext = MemoryUsage.from_crawler(crawler)

        with patch.object(ext, "get_virtual_size", return_value=low_mem):
            await crawler._apply_settings()
            crawler.stats.open_spider(None)
            ext.engine_started()
            ext._check_warning()
            ext.engine_stopped()

        assert crawler.stats.get_value("memusage/warning_reached") is None
        assert ext.warned is False


class TestMemoryUsageLimitThreshold:
    """Memory exceeds the hard limit → spider is closed and stat is set."""

    @coroutine_test
    async def test_limit_stat_set_when_threshold_exceeded(self):
        crawler = _make_crawler(
            {
                "MEMUSAGE_WARNING_MB": 0,  # no warning
                "MEMUSAGE_LIMIT_MB": 100,
                "MEMUSAGE_CHECK_INTERVAL_SECONDS": 60.0,
            }
        )
        high_mem = 200 * 1024 * 1024  # 200 MiB > 100 MiB limit

        resource_mock = MagicMock()
        resource_mock.getrusage.return_value.ru_maxrss = high_mem
        resource_mock.RUSAGE_SELF = 0

        with patch("importlib.import_module", return_value=resource_mock):
            ext = MemoryUsage.from_crawler(crawler)

        # Mock the engine so _check_limit can reference it
        mock_engine = MagicMock()
        mock_engine.spider = None
        crawler.engine = mock_engine

        with patch.object(ext, "get_virtual_size", return_value=high_mem):
            with patch(
                "scrapy.extensions.memusage._schedule_coro"
            ) as mock_schedule:
                await crawler._apply_settings()
                crawler.stats.open_spider(None)
                ext.engine_started()
                ext._check_limit()
                ext.engine_stopped()

        assert crawler.stats.get_value("memusage/limit_reached") == 1
        # stop_async should have been scheduled
        mock_schedule.assert_called_once()

    @coroutine_test
    async def test_limit_closes_spider_when_spider_is_set(self):
        crawler = _make_crawler(
            {
                "MEMUSAGE_WARNING_MB": 0,
                "MEMUSAGE_LIMIT_MB": 100,
                "MEMUSAGE_CHECK_INTERVAL_SECONDS": 60.0,
            }
        )
        high_mem = 200 * 1024 * 1024

        resource_mock = MagicMock()
        resource_mock.getrusage.return_value.ru_maxrss = high_mem
        resource_mock.RUSAGE_SELF = 0

        with patch("importlib.import_module", return_value=resource_mock):
            ext = MemoryUsage.from_crawler(crawler)

        mock_spider = MagicMock()
        mock_engine = MagicMock()
        mock_engine.spider = mock_spider
        crawler.engine = mock_engine

        with patch.object(ext, "get_virtual_size", return_value=high_mem):
            with patch(
                "scrapy.extensions.memusage._schedule_coro"
            ) as mock_schedule:
                await crawler._apply_settings()
                crawler.stats.open_spider(None)
                ext.engine_started()
                ext._check_limit()
                ext.engine_stopped()

        assert crawler.stats.get_value("memusage/limit_reached") == 1
        mock_schedule.assert_called_once()
        # close_spider_async should have been called with "memusage_exceeded"
        mock_engine.close_spider_async.assert_called_once_with(
            reason="memusage_exceeded"
        )

    @coroutine_test
    async def test_no_limit_action_when_below_threshold(self):
        crawler = _make_crawler(
            {
                "MEMUSAGE_WARNING_MB": 0,
                "MEMUSAGE_LIMIT_MB": 100,
                "MEMUSAGE_CHECK_INTERVAL_SECONDS": 60.0,
            }
        )
        low_mem = 50 * 1024 * 1024  # 50 MiB < 100 MiB limit

        resource_mock = MagicMock()
        resource_mock.getrusage.return_value.ru_maxrss = low_mem
        resource_mock.RUSAGE_SELF = 0

        with patch("importlib.import_module", return_value=resource_mock):
            ext = MemoryUsage.from_crawler(crawler)

        mock_engine = MagicMock()
        mock_engine.spider = None
        crawler.engine = mock_engine

        with patch.object(ext, "get_virtual_size", return_value=low_mem):
            with patch(
                "scrapy.extensions.memusage._schedule_coro"
            ) as mock_schedule:
                await crawler._apply_settings()
                crawler.stats.open_spider(None)
                ext.engine_started()
                ext._check_limit()
                ext.engine_stopped()

        assert crawler.stats.get_value("memusage/limit_reached") is None
        mock_schedule.assert_not_called()


class TestMemoryUsageUpdateStats:
    """Tests for the update() method which tracks max memory usage."""

    @coroutine_test
    async def test_update_sets_max_stat(self):
        crawler = _make_crawler()
        mem_value = 128 * 1024 * 1024  # 128 MiB

        resource_mock = MagicMock()
        resource_mock.getrusage.return_value.ru_maxrss = mem_value
        resource_mock.RUSAGE_SELF = 0

        with patch("importlib.import_module", return_value=resource_mock):
            ext = MemoryUsage.from_crawler(crawler)

        with patch.object(ext, "get_virtual_size", return_value=mem_value):
            await crawler._apply_settings()
            crawler.stats.open_spider(None)
            ext.update()

        assert crawler.stats.get_value("memusage/max") == mem_value

    @coroutine_test
    async def test_update_tracks_maximum_across_calls(self):
        """max_value ensures only the highest value is kept."""
        crawler = _make_crawler()

        resource_mock = MagicMock()
        resource_mock.getrusage.return_value.ru_maxrss = 0
        resource_mock.RUSAGE_SELF = 0

        with patch("importlib.import_module", return_value=resource_mock):
            ext = MemoryUsage.from_crawler(crawler)

        await crawler._apply_settings()
        crawler.stats.open_spider(None)

        with patch.object(ext, "get_virtual_size", return_value=100 * 1024 * 1024):
            ext.update()
        with patch.object(ext, "get_virtual_size", return_value=200 * 1024 * 1024):
            ext.update()
        with patch.object(ext, "get_virtual_size", return_value=50 * 1024 * 1024):
            ext.update()

        assert crawler.stats.get_value("memusage/max") == 200 * 1024 * 1024
