from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler as _get_crawler


def get_crawler(settings=None):
    settings = settings or {}
    settings.setdefault("MEMUSAGE_ENABLED", True)
    return _get_crawler(settings_dict=settings)


class TestMemoryUsageInit:
    """Tests for MemoryUsage initialization and configuration."""

    def test_not_configured_when_disabled(self):
        crawler = _get_crawler(settings_dict={"MEMUSAGE_ENABLED": False})
        with pytest.raises(NotConfigured):
            build_from_crawler(MemoryUsage, crawler)

    @patch.dict("sys.modules", {"resource": None})
    def test_not_configured_when_resource_unavailable(self):
        """Extension raises NotConfigured when resource module is not available."""
        crawler = get_crawler()
        with pytest.raises(NotConfigured):
            build_from_crawler(MemoryUsage, crawler)

    def test_default_settings(self):
        crawler = get_crawler()
        ext = build_from_crawler(MemoryUsage, crawler)
        assert ext.warned is False
        assert ext.notify_mails == []
        assert ext.limit == 0  # MEMUSAGE_LIMIT_MB defaults to 0
        assert ext.warning == 0  # MEMUSAGE_WARNING_MB defaults to 0
        assert ext.check_interval == 60.0

    def test_custom_limit(self):
        crawler = get_crawler({"MEMUSAGE_LIMIT_MB": 512})
        ext = build_from_crawler(MemoryUsage, crawler)
        assert ext.limit == 512 * 1024 * 1024

    def test_custom_warning(self):
        crawler = get_crawler({"MEMUSAGE_WARNING_MB": 256})
        ext = build_from_crawler(MemoryUsage, crawler)
        assert ext.warning == 256 * 1024 * 1024

    def test_custom_check_interval(self):
        crawler = get_crawler({"MEMUSAGE_CHECK_INTERVAL_SECONDS": 30.0})
        ext = build_from_crawler(MemoryUsage, crawler)
        assert ext.check_interval == 30.0

    def test_from_crawler(self):
        crawler = get_crawler()
        ext = MemoryUsage.from_crawler(crawler)
        assert isinstance(ext, MemoryUsage)
        assert ext.crawler is crawler


class TestMemoryUsageUpdate:
    """Tests for the update() method that tracks max memory."""

    def test_update_sets_max_stat(self):
        crawler = get_crawler()
        ext = build_from_crawler(MemoryUsage, crawler)
        with patch.object(ext, "get_virtual_size", return_value=100 * 1024 * 1024):
            ext.update()
        assert crawler.stats.get_value("memusage/max") == 100 * 1024 * 1024

    def test_update_tracks_maximum(self):
        crawler = get_crawler()
        ext = build_from_crawler(MemoryUsage, crawler)
        with patch.object(ext, "get_virtual_size", return_value=200 * 1024 * 1024):
            ext.update()
        with patch.object(ext, "get_virtual_size", return_value=100 * 1024 * 1024):
            ext.update()
        # max_value should keep the highest value
        assert crawler.stats.get_value("memusage/max") == 200 * 1024 * 1024


class TestMemoryUsageCheckLimit:
    """Tests for memory limit checking and spider shutdown."""

    def test_no_shutdown_under_limit(self):
        crawler = get_crawler({"MEMUSAGE_LIMIT_MB": 512})
        ext = build_from_crawler(MemoryUsage, crawler)
        crawler.engine = MagicMock()
        mem_under_limit = 256 * 1024 * 1024
        with patch.object(ext, "get_virtual_size", return_value=mem_under_limit):
            ext._check_limit()
        assert crawler.stats.get_value("memusage/limit_reached") is None

    def test_shutdown_when_limit_exceeded_with_spider(self):
        crawler = get_crawler({"MEMUSAGE_LIMIT_MB": 512})
        ext = build_from_crawler(MemoryUsage, crawler)
        crawler.engine = MagicMock()
        crawler.engine.spider = MagicMock()
        mem_over_limit = 600 * 1024 * 1024
        with (
            patch.object(ext, "get_virtual_size", return_value=mem_over_limit),
            patch(
                "scrapy.extensions.memusage._schedule_coro"
            ) as mock_schedule,
        ):
            ext._check_limit()
        assert crawler.stats.get_value("memusage/limit_reached") == 1
        mock_schedule.assert_called_once()

    def test_shutdown_when_limit_exceeded_no_spider(self):
        crawler = get_crawler({"MEMUSAGE_LIMIT_MB": 512})
        ext = build_from_crawler(MemoryUsage, crawler)
        crawler.engine = MagicMock()
        crawler.engine.spider = None
        mem_over_limit = 600 * 1024 * 1024
        with (
            patch.object(ext, "get_virtual_size", return_value=mem_over_limit),
            patch(
                "scrapy.extensions.memusage._schedule_coro"
            ) as mock_schedule,
        ):
            ext._check_limit()
        assert crawler.stats.get_value("memusage/limit_reached") == 1
        mock_schedule.assert_called_once()

    def test_limit_exceeded_logs_error(self, caplog):
        crawler = get_crawler({"MEMUSAGE_LIMIT_MB": 512})
        ext = build_from_crawler(MemoryUsage, crawler)
        crawler.engine = MagicMock()
        mem_over_limit = 600 * 1024 * 1024
        with (
            patch.object(ext, "get_virtual_size", return_value=mem_over_limit),
            patch("scrapy.extensions.memusage._schedule_coro"),
            caplog.at_level(logging.ERROR),
        ):
            ext._check_limit()
        assert any("Memory usage exceeded" in r.message for r in caplog.records)

    def test_under_limit_logs_info(self, caplog):
        crawler = get_crawler({"MEMUSAGE_LIMIT_MB": 512})
        ext = build_from_crawler(MemoryUsage, crawler)
        crawler.engine = MagicMock()
        mem_under_limit = 256 * 1024 * 1024
        with (
            patch.object(ext, "get_virtual_size", return_value=mem_under_limit),
            caplog.at_level(logging.INFO),
        ):
            ext._check_limit()
        assert any("Peak memory usage" in r.message for r in caplog.records)


class TestMemoryUsageCheckWarning:
    """Tests for memory warning checking."""

    def test_no_warning_under_threshold(self):
        crawler = get_crawler({"MEMUSAGE_WARNING_MB": 256})
        ext = build_from_crawler(MemoryUsage, crawler)
        mem_under_warning = 128 * 1024 * 1024
        with patch.object(ext, "get_virtual_size", return_value=mem_under_warning):
            ext._check_warning()
        assert ext.warned is False
        assert crawler.stats.get_value("memusage/warning_reached") is None

    def test_warning_when_threshold_exceeded(self):
        crawler = get_crawler({"MEMUSAGE_WARNING_MB": 256})
        ext = build_from_crawler(MemoryUsage, crawler)
        mem_over_warning = 300 * 1024 * 1024
        with patch.object(ext, "get_virtual_size", return_value=mem_over_warning):
            ext._check_warning()
        assert ext.warned is True
        assert crawler.stats.get_value("memusage/warning_reached") == 1

    def test_warning_only_once(self):
        crawler = get_crawler({"MEMUSAGE_WARNING_MB": 256})
        ext = build_from_crawler(MemoryUsage, crawler)
        mem_over_warning = 300 * 1024 * 1024
        with patch.object(ext, "get_virtual_size", return_value=mem_over_warning):
            ext._check_warning()
            ext._check_warning()
        # The signal should have been sent only once because warned is set to True
        assert ext.warned is True

    def test_warning_logs_message(self, caplog):
        crawler = get_crawler({"MEMUSAGE_WARNING_MB": 256})
        ext = build_from_crawler(MemoryUsage, crawler)
        mem_over_warning = 300 * 1024 * 1024
        with (
            patch.object(ext, "get_virtual_size", return_value=mem_over_warning),
            caplog.at_level(logging.WARNING),
        ):
            ext._check_warning()
        assert any("Memory usage reached" in r.message for r in caplog.records)

    def test_warning_sends_signal(self):
        crawler = get_crawler({"MEMUSAGE_WARNING_MB": 256})
        ext = build_from_crawler(MemoryUsage, crawler)
        signal_received = []

        from scrapy import signals

        crawler.signals.connect(
            lambda: signal_received.append(True),
            signal=signals.memusage_warning_reached,
        )
        mem_over_warning = 300 * 1024 * 1024
        with patch.object(ext, "get_virtual_size", return_value=mem_over_warning):
            ext._check_warning()
        assert len(signal_received) == 1


class TestMemoryUsageGetVirtualSize:
    """Tests for the get_virtual_size method."""

    def test_get_virtual_size_darwin(self):
        crawler = get_crawler()
        ext = build_from_crawler(MemoryUsage, crawler)
        mock_rusage = MagicMock()
        mock_rusage.ru_maxrss = 100 * 1024 * 1024  # bytes on macOS
        ext.resource = MagicMock()
        ext.resource.getrusage.return_value = mock_rusage
        ext.resource.RUSAGE_SELF = 0
        with patch("scrapy.extensions.memusage.sys") as mock_sys:
            mock_sys.platform = "darwin"
            size = ext.get_virtual_size()
        # On macOS, ru_maxrss is already in bytes
        assert size == 100 * 1024 * 1024

    def test_get_virtual_size_linux(self):
        crawler = get_crawler()
        ext = build_from_crawler(MemoryUsage, crawler)
        mock_rusage = MagicMock()
        mock_rusage.ru_maxrss = 100 * 1024  # KB on Linux
        ext.resource = MagicMock()
        ext.resource.getrusage.return_value = mock_rusage
        ext.resource.RUSAGE_SELF = 0
        with patch("scrapy.extensions.memusage.sys") as mock_sys:
            mock_sys.platform = "linux"
            size = ext.get_virtual_size()
        # On Linux, ru_maxrss is in KB, so it gets multiplied by 1024
        assert size == 100 * 1024 * 1024


class TestMemoryUsageEngineStarted:
    """Tests for engine_started behavior."""

    def test_engine_started_sets_startup_stat(self):
        crawler = get_crawler({"MEMUSAGE_LIMIT_MB": 0, "MEMUSAGE_WARNING_MB": 0})
        ext = build_from_crawler(MemoryUsage, crawler)
        startup_mem = 50 * 1024 * 1024
        with (
            patch.object(ext, "get_virtual_size", return_value=startup_mem),
            patch("scrapy.extensions.memusage.create_looping_call") as mock_lc,
        ):
            mock_task = MagicMock()
            mock_lc.return_value = mock_task
            ext.engine_started()
        assert crawler.stats.get_value("memusage/startup") == startup_mem

    def test_engine_started_creates_update_task(self):
        crawler = get_crawler({"MEMUSAGE_LIMIT_MB": 0, "MEMUSAGE_WARNING_MB": 0})
        ext = build_from_crawler(MemoryUsage, crawler)
        with (
            patch.object(ext, "get_virtual_size", return_value=0),
            patch("scrapy.extensions.memusage.create_looping_call") as mock_lc,
        ):
            mock_task = MagicMock()
            mock_lc.return_value = mock_task
            ext.engine_started()
        # With limit=0 and warning=0, only the update task should be created
        assert mock_lc.call_count == 1
        mock_task.start.assert_called_once_with(ext.check_interval, now=True)

    def test_engine_started_creates_limit_task(self):
        crawler = get_crawler({"MEMUSAGE_LIMIT_MB": 512, "MEMUSAGE_WARNING_MB": 0})
        ext = build_from_crawler(MemoryUsage, crawler)
        with (
            patch.object(ext, "get_virtual_size", return_value=0),
            patch("scrapy.extensions.memusage.create_looping_call") as mock_lc,
        ):
            mock_task = MagicMock()
            mock_lc.return_value = mock_task
            ext.engine_started()
        # update + limit tasks
        assert mock_lc.call_count == 2

    def test_engine_started_creates_warning_task(self):
        crawler = get_crawler({"MEMUSAGE_LIMIT_MB": 0, "MEMUSAGE_WARNING_MB": 256})
        ext = build_from_crawler(MemoryUsage, crawler)
        with (
            patch.object(ext, "get_virtual_size", return_value=0),
            patch("scrapy.extensions.memusage.create_looping_call") as mock_lc,
        ):
            mock_task = MagicMock()
            mock_lc.return_value = mock_task
            ext.engine_started()
        # update + warning tasks
        assert mock_lc.call_count == 2

    def test_engine_started_creates_all_tasks(self):
        crawler = get_crawler({"MEMUSAGE_LIMIT_MB": 512, "MEMUSAGE_WARNING_MB": 256})
        ext = build_from_crawler(MemoryUsage, crawler)
        with (
            patch.object(ext, "get_virtual_size", return_value=0),
            patch("scrapy.extensions.memusage.create_looping_call") as mock_lc,
        ):
            mock_task = MagicMock()
            mock_lc.return_value = mock_task
            ext.engine_started()
        # update + limit + warning tasks
        assert mock_lc.call_count == 3


class TestMemoryUsageEngineStopped:
    """Tests for engine_stopped behavior."""

    def test_engine_stopped_stops_running_tasks(self):
        crawler = get_crawler()
        ext = build_from_crawler(MemoryUsage, crawler)
        task1 = MagicMock()
        task1.running = True
        task2 = MagicMock()
        task2.running = False
        ext.tasks = [task1, task2]
        ext.engine_stopped()
        task1.stop.assert_called_once()
        task2.stop.assert_not_called()
