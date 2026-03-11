from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.test import get_crawler


def _create_memusage(settings_dict=None):
    """Helper to create a MemoryUsage extension with mocked resource module."""
    settings = {"MEMUSAGE_ENABLED": True, **(settings_dict or {})}
    crawler = get_crawler(settings_dict=settings)

    mock_resource = MagicMock()
    mock_resource.RUSAGE_SELF = 0
    mock_resource.getrusage.return_value.ru_maxrss = 100 * 1024

    with (
        patch("scrapy.extensions.memusage.import_module", return_value=mock_resource),
        patch(
            "scrapy.extensions.memusage.MailSender.from_crawler",
            return_value=MagicMock(),
        ),
    ):
        ext = MemoryUsage(crawler)

    return ext, crawler, mock_resource


def test_not_configured_when_disabled():
    crawler = get_crawler(settings_dict={"MEMUSAGE_ENABLED": False})
    with pytest.raises(NotConfigured):
        MemoryUsage(crawler)


def test_not_configured_when_no_resource_module():
    crawler = get_crawler(settings_dict={"MEMUSAGE_ENABLED": True})
    with (
        patch("scrapy.extensions.memusage.import_module", side_effect=ImportError),
        pytest.raises(NotConfigured),
    ):
        MemoryUsage(crawler)


def test_get_virtual_size():
    ext, _, mock_resource = _create_memusage()
    mock_resource.getrusage.return_value.ru_maxrss = 200

    # Linux: ru_maxrss is in KB, so it gets multiplied by 1024
    with patch("scrapy.extensions.memusage.sys") as mock_sys:
        mock_sys.platform = "linux"
        assert ext.get_virtual_size() == 200 * 1024

    # macOS: ru_maxrss is already in bytes
    with patch("scrapy.extensions.memusage.sys") as mock_sys:
        mock_sys.platform = "darwin"
        assert ext.get_virtual_size() == 200


def test_update_sets_max_stat():
    ext, crawler, _ = _create_memusage()

    with patch.object(ext, "get_virtual_size", return_value=50 * 1024 * 1024):
        ext.update()
    assert crawler.stats.get_value("memusage/max") == 50 * 1024 * 1024

    # a smaller value shouldn't replace the max
    with patch.object(ext, "get_virtual_size", return_value=30 * 1024 * 1024):
        ext.update()
    assert crawler.stats.get_value("memusage/max") == 50 * 1024 * 1024


def test_check_limit_exceeded(caplog):
    ext, crawler, _ = _create_memusage({"MEMUSAGE_LIMIT_MB": 100})
    crawler.engine = MagicMock()
    crawler.engine.spider = MagicMock()

    with (
        patch.object(ext, "get_virtual_size", return_value=200 * 1024 * 1024),
        patch("scrapy.extensions.memusage._schedule_coro") as mock_schedule,
        caplog.at_level(logging.ERROR, logger="scrapy.extensions.memusage"),
    ):
        ext._check_limit()

    assert crawler.stats.get_value("memusage/limit_reached") == 1
    assert mock_schedule.called
    crawler.engine.close_spider_async.assert_called_once_with(
        reason="memusage_exceeded"
    )
    assert "Memory usage exceeded" in caplog.text


def test_check_limit_not_exceeded(caplog):
    ext, crawler, _ = _create_memusage({"MEMUSAGE_LIMIT_MB": 100})
    crawler.engine = MagicMock()

    with (
        patch.object(ext, "get_virtual_size", return_value=50 * 1024 * 1024),
        patch("scrapy.extensions.memusage._schedule_coro") as mock_schedule,
        caplog.at_level(logging.INFO, logger="scrapy.extensions.memusage"),
    ):
        ext._check_limit()

    assert crawler.stats.get_value("memusage/limit_reached") is None
    assert not mock_schedule.called
    assert "Peak memory usage is" in caplog.text


def test_check_warning_reached(caplog):
    ext, crawler, _ = _create_memusage({"MEMUSAGE_WARNING_MB": 100})

    with (
        patch.object(ext, "get_virtual_size", return_value=200 * 1024 * 1024),
        caplog.at_level(logging.WARNING, logger="scrapy.extensions.memusage"),
    ):
        ext._check_warning()

    assert crawler.stats.get_value("memusage/warning_reached") == 1
    assert ext.warned is True
    assert "Memory usage reached" in caplog.text


def test_check_warning_only_once():
    ext, _crawler, _ = _create_memusage({"MEMUSAGE_WARNING_MB": 100})

    with patch.object(
        ext, "get_virtual_size", return_value=200 * 1024 * 1024
    ) as mock_gvs:
        ext._check_warning()
        assert mock_gvs.call_count == 1
        # second call should be a no-op because self.warned is True
        ext._check_warning()
        assert mock_gvs.call_count == 1

    assert ext.warned is True


def test_check_limit_sends_email():
    ext, crawler, _ = _create_memusage(
        {"MEMUSAGE_LIMIT_MB": 100, "MEMUSAGE_NOTIFY_MAIL": ["admin@example.com"]}
    )
    crawler.engine = MagicMock()
    crawler.engine.spider = MagicMock()

    with (
        patch.object(ext, "get_virtual_size", return_value=200 * 1024 * 1024),
        patch.object(ext, "_send_report") as mock_send,
        patch("scrapy.extensions.memusage._schedule_coro"),
    ):
        ext._check_limit()

    mock_send.assert_called_once()
    assert mock_send.call_args[0][0] == ["admin@example.com"]
    assert "terminated" in mock_send.call_args[0][1]
    assert crawler.stats.get_value("memusage/limit_notified") == 1


def test_check_warning_sends_email():
    ext, crawler, _ = _create_memusage(
        {"MEMUSAGE_WARNING_MB": 100, "MEMUSAGE_NOTIFY_MAIL": ["admin@example.com"]}
    )

    with (
        patch.object(ext, "get_virtual_size", return_value=200 * 1024 * 1024),
        patch.object(ext, "_send_report") as mock_send,
    ):
        ext._check_warning()

    mock_send.assert_called_once()
    assert mock_send.call_args[0][0] == ["admin@example.com"]
    assert "warning" in mock_send.call_args[0][1]
    assert crawler.stats.get_value("memusage/warning_notified") == 1


def test_engine_started_creates_tasks():
    ext, crawler, _ = _create_memusage(
        {"MEMUSAGE_LIMIT_MB": 100, "MEMUSAGE_WARNING_MB": 50}
    )

    mock_task = MagicMock()
    with (
        patch(
            "scrapy.extensions.memusage.create_looping_call", return_value=mock_task
        ) as mock_clc,
        patch.object(ext, "get_virtual_size", return_value=10 * 1024 * 1024),
    ):
        ext.engine_started()

    # should create 3 tasks: update, _check_limit, _check_warning
    assert mock_clc.call_count == 3
    assert len(ext.tasks) == 3
    assert mock_task.start.call_count == 3
    assert crawler.stats.get_value("memusage/startup") == 10 * 1024 * 1024


def test_engine_stopped_stops_tasks():
    ext, _, _ = _create_memusage()

    running_task = MagicMock(running=True)
    stopped_task = MagicMock(running=False)
    ext.tasks = [running_task, stopped_task]

    ext.engine_stopped()

    running_task.stop.assert_called_once()
    stopped_task.stop.assert_not_called()
