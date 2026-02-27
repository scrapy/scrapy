"""Tests for scrapy.extensions.memusage.MemoryUsage."""

from __future__ import annotations

import sys
from unittest.mock import Mock, patch

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.statscollectors import MemoryStatsCollector
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_extension(
    limit_mb: int = 0,
    warning_mb: int = 0,
    notify_mails: list[str] | None = None,
    check_interval: float = 60.0,
) -> MemoryUsage:
    """Build a real MemoryUsage extension via build_from_crawler."""
    settings: dict = {
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_LIMIT_MB": limit_mb,
        "MEMUSAGE_WARNING_MB": warning_mb,
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": check_interval,
    }
    if notify_mails:
        settings["MEMUSAGE_NOTIFY_MAIL"] = notify_mails
    crawler = get_crawler(settings_dict=settings)
    return build_from_crawler(MemoryUsage, crawler)


# ---------------------------------------------------------------------------
# NotConfigured guards
# ---------------------------------------------------------------------------


def test_not_configured_when_disabled():
    """MemoryUsage raises NotConfigured when MEMUSAGE_ENABLED is False."""
    crawler = get_crawler(settings_dict={"MEMUSAGE_ENABLED": False})
    with pytest.raises(NotConfigured):
        build_from_crawler(MemoryUsage, crawler)


@pytest.mark.skipif(sys.platform != "win32", reason="resource unavailable only on Windows")
def test_not_configured_when_resource_unavailable():
    """MemoryUsage raises NotConfigured when the 'resource' module is missing."""
    crawler = get_crawler(settings_dict={"MEMUSAGE_ENABLED": True})
    with pytest.raises(NotConfigured):
        build_from_crawler(MemoryUsage, crawler)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def test_from_crawler_returns_instance():
    """from_crawler() should return a MemoryUsage instance."""
    ext = make_extension()
    assert isinstance(ext, MemoryUsage)


def test_initialisation_stores_limit():
    """Constructor should convert MEMUSAGE_LIMIT_MB to bytes."""
    ext = make_extension(limit_mb=512)
    assert ext.limit == 512 * 1024 * 1024


def test_initialisation_stores_warning():
    """Constructor should convert MEMUSAGE_WARNING_MB to bytes."""
    ext = make_extension(warning_mb=256)
    assert ext.warning == 256 * 1024 * 1024


def test_initialisation_stores_notify_mails():
    """Constructor should store MEMUSAGE_NOTIFY_MAIL."""
    ext = make_extension(notify_mails=["ops@example.com"])
    assert ext.notify_mails == ["ops@example.com"]


# ---------------------------------------------------------------------------
# get_virtual_size
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="resource module not available")
def test_get_virtual_size_returns_positive_int():
    """get_virtual_size() should return a positive integer (bytes)."""
    ext = make_extension()
    size = ext.get_virtual_size()
    assert isinstance(size, int)
    assert size > 0


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def test_update_records_max_stat():
    """update() should record the current memory reading as memusage/max."""
    ext = make_extension()
    ext.get_virtual_size = Mock(return_value=50 * 1024 * 1024)

    ext.update()

    assert ext.crawler.stats.get_value("memusage/max") == 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# _check_limit
# ---------------------------------------------------------------------------


def test_check_limit_below_limit_logs_info(caplog):
    """When memory is below the limit an INFO message should be emitted."""
    import logging

    ext = make_extension(limit_mb=200)
    ext.get_virtual_size = Mock(return_value=100 * 1024 * 1024)

    with caplog.at_level(logging.INFO, logger="scrapy.extensions.memusage"):
        ext._check_limit()

    assert "Peak memory usage" in caplog.text
    assert ext.crawler.stats.get_value("memusage/limit_reached") is None


def test_check_limit_exceeded_sets_stat(caplog):
    """When memory exceeds the limit the stat memusage/limit_reached is set."""
    import logging

    ext = make_extension(limit_mb=100)
    ext.get_virtual_size = Mock(return_value=200 * 1024 * 1024)
    ext.crawler.engine = Mock()
    ext.crawler.engine.spider = None

    with patch("scrapy.extensions.memusage._schedule_coro"):
        with caplog.at_level(logging.ERROR, logger="scrapy.extensions.memusage"):
            ext._check_limit()

    assert ext.crawler.stats.get_value("memusage/limit_reached") == 1
    assert "exceeded" in caplog.text.lower()


def test_check_limit_exceeded_sends_mail_when_configured():
    """When the limit is exceeded and notify_mails is set a mail is sent."""
    ext = make_extension(limit_mb=100, notify_mails=["ops@example.com"])
    ext.get_virtual_size = Mock(return_value=200 * 1024 * 1024)
    ext.crawler.engine = Mock()
    ext.crawler.engine.spider = None
    ext.mail = Mock()

    with patch("scrapy.extensions.memusage._schedule_coro"):
        ext._check_limit()

    ext.mail.send.assert_called_once()
    assert ext.crawler.stats.get_value("memusage/limit_notified") == 1


# ---------------------------------------------------------------------------
# _check_warning
# ---------------------------------------------------------------------------


def test_check_warning_below_threshold_does_nothing():
    """No stat or log when memory is below the warning threshold."""
    ext = make_extension(warning_mb=256)
    ext.get_virtual_size = Mock(return_value=100 * 1024 * 1024)

    ext._check_warning()

    assert ext.crawler.stats.get_value("memusage/warning_reached") is None
    assert not ext.warned


def test_check_warning_exceeded_sets_stat(caplog):
    """When memory exceeds the warning the stat memusage/warning_reached is set."""
    import logging

    ext = make_extension(warning_mb=100)
    ext.get_virtual_size = Mock(return_value=200 * 1024 * 1024)

    with caplog.at_level(logging.WARNING, logger="scrapy.extensions.memusage"):
        ext._check_warning()

    assert ext.crawler.stats.get_value("memusage/warning_reached") == 1
    assert ext.warned is True
    assert "reached" in caplog.text.lower()


def test_check_warning_fires_only_once():
    """The warning stat must be set exactly once regardless of call count."""
    ext = make_extension(warning_mb=100)
    ext.get_virtual_size = Mock(return_value=200 * 1024 * 1024)

    for _ in range(3):
        ext._check_warning()

    # MemoryStatsCollector stores a single value per key
    assert ext.crawler.stats.get_value("memusage/warning_reached") == 1


def test_check_warning_sends_mail_when_configured():
    """When the warning is exceeded and notify_mails is set a mail is sent."""
    ext = make_extension(warning_mb=100, notify_mails=["ops@example.com"])
    ext.get_virtual_size = Mock(return_value=200 * 1024 * 1024)
    ext.mail = Mock()

    ext._check_warning()

    ext.mail.send.assert_called_once()
    assert ext.crawler.stats.get_value("memusage/warning_notified") == 1


# ---------------------------------------------------------------------------
# engine_started / engine_stopped
# ---------------------------------------------------------------------------


def test_engine_started_records_startup_memory():
    """engine_started() should write the startup memory size to stats."""
    ext = make_extension()
    ext.get_virtual_size = Mock(return_value=42 * 1024 * 1024)

    with patch("scrapy.extensions.memusage.create_looping_call") as mock_loop:
        mock_loop.return_value = Mock()
        ext.engine_started()

    assert ext.crawler.stats.get_value("memusage/startup") == 42 * 1024 * 1024


def test_engine_stopped_stops_only_running_tasks():
    """engine_stopped() should call stop() only on tasks that are running."""
    ext = make_extension()

    running_task = Mock()
    running_task.running = True
    stopped_task = Mock()
    stopped_task.running = False
    ext.tasks = [running_task, stopped_task]

    ext.engine_stopped()

    running_task.stop.assert_called_once()
    stopped_task.stop.assert_not_called()
