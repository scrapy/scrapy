import types

import pytest

import scrapy.extensions.memusage as memusage_mod
from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.test import get_crawler

MB = 1024 * 1024


def make_crawler(settings_dict=None):
    # Small helper to build a Scrapy crawler with custom settings for unit tests.
    settings_dict = settings_dict or {}
    return get_crawler(settings_dict=settings_dict)


def make_enabled_extension(monkeypatch, crawler):
    """
    Windows is missing the `resource` module, so MemoryUsage turns itself off by default.
    We fake that import in the test so we can still test what the extension does.
    """
    fake_resource = types.SimpleNamespace()
    monkeypatch.setattr(memusage_mod, "import_module", lambda name: fake_resource)
    return MemoryUsage.from_crawler(crawler)


def test_not_configured_if_disabled():
    # If MEMUSAGE_ENABLED is False, the extension should not be active.
    crawler = make_crawler({"MEMUSAGE_ENABLED": False})
    with pytest.raises(NotConfigured):
        MemoryUsage.from_crawler(crawler)


def test_update_sets_memusage_max(monkeypatch):
    # update() should record the maximum observed memory usage in stats.
    crawler = make_crawler({"MEMUSAGE_ENABLED": True})
    ext = make_enabled_extension(monkeypatch, crawler)

    # Simulate memory increasing across calls (bytes).
    values = iter([10_000_000, 20_000_000])
    monkeypatch.setattr(ext, "get_virtual_size", lambda: next(values))

    ext.update()
    ext.update()

    assert crawler.stats.get_value("memusage/max") == 20_000_000


def test_check_warning_sets_flag_and_stat_once(monkeypatch):
    # If memory exceeds the warning threshold, the warning stat should be set.
    # It should only warn once.
    crawler = make_crawler(
        {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 1,
            "MEMUSAGE_NOTIFY_MAIL": [],
        }
    )
    ext = make_enabled_extension(monkeypatch, crawler)

    monkeypatch.setattr(ext, "get_virtual_size", lambda: 2 * MB)

    ext._check_warning()
    assert crawler.stats.get_value("memusage/warning_reached") == 1

    # Calling again shouldn't re-trigger the warning behavior.
    ext._check_warning()
    assert crawler.stats.get_value("memusage/warning_reached") == 1


def test_check_limit_sets_flag_and_schedules_close(monkeypatch):
    """
    If memory exceeds the hard limit, the extension should:
    - set the "limit reached" stat
    - initiate a spider close with the expected reason
    """
    crawler = make_crawler(
        {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 1,
            "MEMUSAGE_NOTIFY_MAIL": [],  # keep this test focused
        }
    )

    # Capture what gets scheduled without depending on async behavior.
    scheduled = {}

    def fake_schedule_coro(coro):
        scheduled["coro"] = coro

    monkeypatch.setattr(memusage_mod, "_schedule_coro", fake_schedule_coro)

    ext = make_enabled_extension(monkeypatch, crawler)

    # Capture the close reason without running a real crawl.
    reason_box = {}

    # Small fake engine so _check_limit can call close_spider_async.
    class DummyEngine:
        spider = object()

        def close_spider_async(self, *, reason):
            reason_box["reason"] = reason
            return "fake_coro"

    crawler.engine = DummyEngine()

    monkeypatch.setattr(ext, "get_virtual_size", lambda: 2 * MB)

    ext._check_limit()

    assert crawler.stats.get_value("memusage/limit_reached") == 1
    assert reason_box["reason"] == "memusage_exceeded"
    assert scheduled["coro"] == "fake_coro"
