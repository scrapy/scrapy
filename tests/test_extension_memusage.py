from unittest.mock import MagicMock, patch

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler


def get_memusage_crawler(settings=None):
    settings = settings or {}
    settings.setdefault("MEMUSAGE_ENABLED", True)
    settings.setdefault("MEMUSAGE_CHECK_INTERVAL_SECONDS", 60.0)
    return get_crawler(settings_dict=settings)


def build_memusage(settings=None):
    crawler = get_memusage_crawler(settings)
    return build_from_crawler(MemoryUsage, crawler), crawler


_100MB = 100 * 1024 * 1024
_200MB = 200 * 1024 * 1024
_300MB = 300 * 1024 * 1024


def test_disabled_by_setting():
    crawler = get_crawler(settings_dict={"MEMUSAGE_ENABLED": False})
    with pytest.raises(NotConfigured):
        build_from_crawler(MemoryUsage, crawler)


def test_enabled():
    ext, _ = build_memusage()
    assert isinstance(ext, MemoryUsage)


def test_engine_started_sets_startup_stat():
    ext, crawler = build_memusage()
    crawler.stats = MagicMock()
    with patch.object(ext, "get_virtual_size", return_value=_100MB):
        ext.engine_started()
    crawler.stats.set_value.assert_called_once_with("memusage/startup", _100MB)


def test_engine_stopped_stops_tasks():
    ext, crawler = build_memusage()
    crawler.stats = MagicMock()
    with patch.object(ext, "get_virtual_size", return_value=_100MB):
        ext.engine_started()
    assert all(tsk.running for tsk in ext.tasks)
    ext.engine_stopped()
    assert all(not tsk.running for tsk in ext.tasks)


def test_update_records_max_memory():
    ext, crawler = build_memusage()
    crawler.stats = MagicMock()
    with patch.object(ext, "get_virtual_size", return_value=_200MB):
        ext.update()
    crawler.stats.max_value.assert_called_once_with("memusage/max", _200MB)


def test_check_warning_below_threshold(caplog):
    ext, crawler = build_memusage({"MEMUSAGE_WARNING_MB": 200})
    crawler.stats = MagicMock()
    with patch.object(ext, "get_virtual_size", return_value=_100MB):
        with caplog.at_level("WARNING", logger="scrapy.extensions.memusage"):
            ext._check_warning()
    assert "Memory usage reached" not in caplog.text
    crawler.stats.set_value.assert_not_called()


def test_check_warning_above_threshold(caplog):
    ext, crawler = build_memusage({"MEMUSAGE_WARNING_MB": 100})
    crawler.stats = MagicMock()
    with patch.object(ext, "get_virtual_size", return_value=_200MB):
        with caplog.at_level("WARNING", logger="scrapy.extensions.memusage"):
            ext._check_warning()
    assert "Memory usage reached" in caplog.text
    crawler.stats.set_value.assert_any_call("memusage/warning_reached", 1)


def test_check_warning_only_warns_once(caplog):
    ext, crawler = build_memusage({"MEMUSAGE_WARNING_MB": 100})
    crawler.stats = MagicMock()
    with patch.object(ext, "get_virtual_size", return_value=_200MB):
        with caplog.at_level("WARNING", logger="scrapy.extensions.memusage"):
            ext._check_warning()
            ext._check_warning()
    warning_calls = [
        c for c in crawler.stats.set_value.call_args_list
        if c.args[0] == "memusage/warning_reached"
    ]
    assert len(warning_calls) == 1


def test_check_limit_below_threshold(caplog):
    ext, crawler = build_memusage({"MEMUSAGE_LIMIT_MB": 300})
    crawler.stats = MagicMock()
    crawler.engine = MagicMock()
    with patch.object(ext, "get_virtual_size", return_value=_100MB):
        with caplog.at_level("INFO", logger="scrapy.extensions.memusage"):
            ext._check_limit()
    assert "Peak memory usage" in caplog.text
    crawler.stats.set_value.assert_not_called()


def test_check_limit_above_threshold(caplog):
    ext, crawler = build_memusage({"MEMUSAGE_LIMIT_MB": 100})
    crawler.stats = MagicMock()
    crawler.engine = MagicMock()
    crawler.engine.spider = MagicMock()
    with patch.object(ext, "get_virtual_size", return_value=_200MB):
        with patch("scrapy.extensions.memusage._schedule_coro"):
            with caplog.at_level("ERROR", logger="scrapy.extensions.memusage"):
                ext._check_limit()
    assert "Memory usage exceeded" in caplog.text
    crawler.stats.set_value.assert_any_call("memusage/limit_reached", 1)


def test_check_limit_closes_spider():
    ext, crawler = build_memusage({"MEMUSAGE_LIMIT_MB": 100})
    crawler.stats = MagicMock()
    crawler.engine = MagicMock()
    crawler.engine.spider = MagicMock()
    with patch.object(ext, "get_virtual_size", return_value=_200MB):
        with patch("scrapy.extensions.memusage._schedule_coro") as mock_schedule:
            ext._check_limit()
    crawler.engine.close_spider_async.assert_called_once_with(reason="memusage_exceeded")
    assert mock_schedule.called


def test_check_limit_stops_crawler_when_no_spider():
    ext, crawler = build_memusage({"MEMUSAGE_LIMIT_MB": 100})
    crawler.stats = MagicMock()
    crawler.engine = MagicMock()
    crawler.engine.spider = None
    with patch.object(ext, "get_virtual_size", return_value=_200MB):
        with patch("scrapy.extensions.memusage._schedule_coro") as mock_schedule:
            with patch.object(crawler, "stop_async", return_value=MagicMock()) as mock_stop:
                ext._check_limit()
    mock_stop.assert_called_once()
    assert mock_schedule.called


def test_no_limit_task_when_limit_is_zero():
    ext, crawler = build_memusage({"MEMUSAGE_LIMIT_MB": 0, "MEMUSAGE_WARNING_MB": 0})
    crawler.stats = MagicMock()
    with patch.object(ext, "get_virtual_size", return_value=_100MB):
        ext.engine_started()
    assert len(ext.tasks) == 1
    ext.engine_stopped()
