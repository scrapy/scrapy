from __future__ import annotations

import logging
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler

from .utils.decorators import inline_callbacks_test

# memusage relies on the stdlib 'resource' module (not available on Windows)
pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="MemoryUsage extension not available on Windows",
)

MB = 1024 * 1024


class _DummySpider(Spider):
    name = "dummy"
    start_urls = ["data:,"]

    def parse(self, response: Any) -> None:
        pass


def _base_settings(**overrides: Any) -> dict[str, Any]:
    """Return base settings suitable for memusage tests."""
    settings: dict[str, Any] = {
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_LIMIT_MB": 0,
        "MEMUSAGE_WARNING_MB": 0,
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 60.0,
        "MEMUSAGE_NOTIFY_MAIL": [],
        "TELNETCONSOLE_ENABLED": False,
    }
    settings.update(overrides)
    return settings


def _engine_started_once(self: MemoryUsage) -> None:
    """Test-only replacement for MemoryUsage.engine_started.

    Runs checks once synchronously without scheduling periodic LoopingCalls,
    avoiding race conditions in tests.
    """
    assert self.crawler.stats
    self.crawler.stats.set_value("memusage/startup", self.get_virtual_size())
    self.tasks = []
    self.update()
    if self.limit:
        self._check_limit()
    if self.warning:
        self._check_warning()


# --- Construction / from_crawler tests ---


def test_not_configured_when_disabled() -> None:
    crawler = get_crawler(settings_dict=_base_settings(MEMUSAGE_ENABLED=False))
    with pytest.raises(NotConfigured):
        build_from_crawler(MemoryUsage, crawler)


def test_not_configured_when_resource_unavailable() -> None:
    crawler = get_crawler(settings_dict=_base_settings())

    def _fail_import(name: str) -> None:
        raise ImportError("no resource module")

    with patch("scrapy.extensions.memusage.import_module", side_effect=_fail_import):
        with pytest.raises(NotConfigured):
            build_from_crawler(MemoryUsage, crawler)


def test_from_crawler_returns_instance() -> None:
    crawler = get_crawler(settings_dict=_base_settings())
    ext = build_from_crawler(MemoryUsage, crawler)
    assert isinstance(ext, MemoryUsage)


def test_settings_parsed_correctly() -> None:
    settings = _base_settings(
        MEMUSAGE_LIMIT_MB=512,
        MEMUSAGE_WARNING_MB=256,
        MEMUSAGE_CHECK_INTERVAL_SECONDS=30.0,
        MEMUSAGE_NOTIFY_MAIL=["admin@example.com"],
    )
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    assert ext.limit == 512 * MB
    assert ext.warning == 256 * MB
    assert ext.check_interval == 30.0
    assert ext.notify_mails == ["admin@example.com"]
    assert ext.warned is False


# --- get_virtual_size ---


def test_get_virtual_size_returns_positive_int() -> None:
    crawler = get_crawler(settings_dict=_base_settings())
    ext = build_from_crawler(MemoryUsage, crawler)
    size = ext.get_virtual_size()
    assert isinstance(size, int)
    assert size > 0


# --- update ---


def test_update_sets_max_stat(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = get_crawler(settings_dict=_base_settings())
    ext = build_from_crawler(MemoryUsage, crawler)
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 100 * MB)
    crawler.stats.set_value("memusage/max", 0)
    ext.update()
    assert crawler.stats.get_value("memusage/max") == 100 * MB


def test_update_keeps_higher_max(monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = get_crawler(settings_dict=_base_settings())
    ext = build_from_crawler(MemoryUsage, crawler)

    monkeypatch.setattr(ext, "get_virtual_size", lambda: 200 * MB)
    ext.update()
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 100 * MB)
    ext.update()
    assert crawler.stats.get_value("memusage/max") == 200 * MB


# --- _check_limit ---


def test_check_limit_no_action_when_under(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _base_settings(MEMUSAGE_LIMIT_MB=512)
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    crawler.engine = MagicMock()
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 256 * MB)

    with caplog.at_level(logging.INFO, logger="scrapy.extensions.memusage"):
        ext._check_limit()

    assert crawler.stats.get_value("memusage/limit_reached") is None
    assert any("peak memory usage" in r.getMessage().lower() for r in caplog.records)


def test_check_limit_exceeded_sets_stat_and_logs_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _base_settings(MEMUSAGE_LIMIT_MB=512)
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    crawler.engine = MagicMock()
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 1024 * MB)

    with patch("scrapy.extensions.memusage._schedule_coro"):
        with caplog.at_level(logging.ERROR, logger="scrapy.extensions.memusage"):
            ext._check_limit()

    assert crawler.stats.get_value("memusage/limit_reached") == 1
    assert any(
        "memory usage exceeded" in r.getMessage().lower() for r in caplog.records
    )


def test_check_limit_exceeded_closes_spider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _base_settings(MEMUSAGE_LIMIT_MB=512)
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    crawler.engine = MagicMock()
    crawler.engine.spider = MagicMock()
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 1024 * MB)

    with patch("scrapy.extensions.memusage._schedule_coro") as mock_schedule:
        ext._check_limit()
        mock_schedule.assert_called_once()


def test_check_limit_exceeded_stops_crawler_when_no_spider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _base_settings(MEMUSAGE_LIMIT_MB=512)
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    crawler.engine = MagicMock()
    crawler.engine.spider = None
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 1024 * MB)

    with patch("scrapy.extensions.memusage._schedule_coro") as mock_schedule:
        ext._check_limit()
        mock_schedule.assert_called_once()


def test_check_limit_exceeded_sends_email(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _base_settings(
        MEMUSAGE_LIMIT_MB=512,
        MEMUSAGE_NOTIFY_MAIL=["admin@example.com"],
    )
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    crawler.engine = MagicMock()
    crawler.stats.set_value("memusage/startup", 100 * MB)
    crawler.stats.set_value("memusage/max", 200 * MB)
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 1024 * MB)
    ext.mail = MagicMock()

    with patch("scrapy.extensions.memusage._schedule_coro"):
        ext._check_limit()

    ext.mail.send.assert_called_once()
    args = ext.mail.send.call_args[0]
    assert args[0] == ["admin@example.com"]
    assert "terminated" in args[1].lower()
    assert "512" in args[1]
    assert crawler.stats.get_value("memusage/limit_notified") == 1


def test_check_limit_exceeded_no_email_without_notify_mails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _base_settings(MEMUSAGE_LIMIT_MB=512)
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    crawler.engine = MagicMock()
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 1024 * MB)
    ext.mail = MagicMock()

    with patch("scrapy.extensions.memusage._schedule_coro"):
        ext._check_limit()

    ext.mail.send.assert_not_called()
    assert crawler.stats.get_value("memusage/limit_notified") is None


# --- _check_warning ---


def test_check_warning_no_action_when_under(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _base_settings(MEMUSAGE_WARNING_MB=512)
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 256 * MB)

    ext._check_warning()

    assert crawler.stats.get_value("memusage/warning_reached") is None
    assert ext.warned is False


def test_check_warning_sets_stat_and_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _base_settings(MEMUSAGE_WARNING_MB=256)
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 512 * MB)

    with caplog.at_level(logging.WARNING, logger="scrapy.extensions.memusage"):
        ext._check_warning()

    assert crawler.stats.get_value("memusage/warning_reached") == 1
    assert ext.warned is True
    assert any(
        "memory usage reached" in r.getMessage().lower() for r in caplog.records
    )


def test_check_warning_only_warns_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _base_settings(MEMUSAGE_WARNING_MB=256)
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 512 * MB)

    with caplog.at_level(logging.WARNING, logger="scrapy.extensions.memusage"):
        ext._check_warning()
        caplog.clear()
        ext._check_warning()

    # Second call should not produce a new warning record
    assert not any(
        "memory usage reached" in r.getMessage().lower() for r in caplog.records
    )


def test_check_warning_sends_email(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _base_settings(
        MEMUSAGE_WARNING_MB=256,
        MEMUSAGE_NOTIFY_MAIL=["admin@example.com"],
    )
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    crawler.engine = MagicMock()
    crawler.stats.set_value("memusage/startup", 100 * MB)
    crawler.stats.set_value("memusage/max", 300 * MB)
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 512 * MB)
    ext.mail = MagicMock()

    ext._check_warning()

    ext.mail.send.assert_called_once()
    args = ext.mail.send.call_args[0]
    assert args[0] == ["admin@example.com"]
    assert "warning" in args[1].lower()
    assert "256" in args[1]
    assert crawler.stats.get_value("memusage/warning_notified") == 1


def test_check_warning_no_email_without_notify_mails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _base_settings(MEMUSAGE_WARNING_MB=256)
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 512 * MB)
    ext.mail = MagicMock()

    ext._check_warning()

    ext.mail.send.assert_not_called()
    assert crawler.stats.get_value("memusage/warning_notified") is None


# --- _send_report ---


def test_send_report_includes_stats_and_engine_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _base_settings(MEMUSAGE_LIMIT_MB=512)
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    crawler.engine = MagicMock()
    crawler.stats.set_value("memusage/startup", 50 * MB)
    crawler.stats.set_value("memusage/max", 100 * MB)
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 200 * MB)
    ext.mail = MagicMock()

    ext._send_report(["admin@example.com"], "Test Subject")

    ext.mail.send.assert_called_once()
    args = ext.mail.send.call_args[0]
    assert args[0] == ["admin@example.com"]
    assert args[1] == "Test Subject"
    body = args[2]
    assert "Memory usage at engine startup" in body
    assert "Maximum memory usage" in body
    assert "Current memory usage" in body
    assert "ENGINE STATUS" in body


# --- engine_started / engine_stopped ---


def test_engine_started_sets_startup_stat(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _base_settings()
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)
    monkeypatch.setattr(ext, "get_virtual_size", lambda: 150 * MB)

    _engine_started_once(ext)

    assert crawler.stats.get_value("memusage/startup") == 150 * MB


def test_engine_stopped_stops_tasks() -> None:
    settings = _base_settings()
    crawler = get_crawler(settings_dict=settings)
    ext = build_from_crawler(MemoryUsage, crawler)

    task1 = MagicMock()
    task1.running = True
    task2 = MagicMock()
    task2.running = False
    ext.tasks = [task1, task2]

    ext.engine_stopped()

    task1.stop.assert_called_once()
    task2.stop.assert_not_called()


# --- Integration tests using crawler.crawl() ---


@inline_callbacks_test
def test_integration_limit_exceeded_closes_spider(
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    """When memory exceeds the limit, the spider closes with reason
    'memusage_exceeded'."""
    settings = _base_settings(
        MEMUSAGE_LIMIT_MB=10,
        MEMUSAGE_CHECK_INTERVAL_SECONDS=0.01,
    )

    monkeypatch.setattr(
        MemoryUsage, "engine_started", _engine_started_once, raising=True
    )
    monkeypatch.setattr(
        MemoryUsage, "get_virtual_size", lambda self: 250 * MB, raising=True
    )

    crawler = get_crawler(spidercls=_DummySpider, settings_dict=settings)
    yield crawler.crawl()

    assert crawler.stats.get_value("finish_reason") == "memusage_exceeded"
    assert crawler.stats.get_value("memusage/limit_reached") == 1


@inline_callbacks_test
def test_integration_warning_logged_but_finishes_normally(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> Any:
    """When memory exceeds the warning threshold but not the limit, the spider
    finishes normally and a warning is logged."""
    settings = _base_settings(
        MEMUSAGE_WARNING_MB=50,
        MEMUSAGE_LIMIT_MB=0,
        MEMUSAGE_CHECK_INTERVAL_SECONDS=0.01,
    )

    monkeypatch.setattr(
        MemoryUsage, "engine_started", _engine_started_once, raising=True
    )
    monkeypatch.setattr(
        MemoryUsage, "get_virtual_size", lambda self: 75 * MB, raising=True
    )

    crawler = get_crawler(spidercls=_DummySpider, settings_dict=settings)

    caplog.set_level(logging.WARNING, logger="scrapy.extensions.memusage")
    yield crawler.crawl()

    assert crawler.stats.get_value("finish_reason") == "finished"
    assert crawler.stats.get_value("memusage/warning_reached") == 1
    assert any(
        "memory usage reached" in r.getMessage().lower() for r in caplog.records
    )


@inline_callbacks_test
def test_integration_limit_exceeded_with_email_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    """When memory exceeds the limit and MEMUSAGE_NOTIFY_MAIL is set,
    an email is sent and the limit_notified stat is set."""
    settings = _base_settings(
        MEMUSAGE_LIMIT_MB=10,
        MEMUSAGE_CHECK_INTERVAL_SECONDS=0.01,
        MEMUSAGE_NOTIFY_MAIL=["admin@example.com"],
    )

    monkeypatch.setattr(
        MemoryUsage, "engine_started", _engine_started_once, raising=True
    )
    monkeypatch.setattr(
        MemoryUsage, "get_virtual_size", lambda self: 250 * MB, raising=True
    )

    mail_mock = MagicMock()
    original_init = MemoryUsage.__init__

    def patched_init(self: MemoryUsage, crawler_arg: Any) -> None:
        original_init(self, crawler_arg)
        self.mail = mail_mock

    monkeypatch.setattr(MemoryUsage, "__init__", patched_init, raising=True)

    crawler = get_crawler(spidercls=_DummySpider, settings_dict=settings)
    yield crawler.crawl()

    assert crawler.stats.get_value("memusage/limit_reached") == 1
    assert crawler.stats.get_value("memusage/limit_notified") == 1
    mail_mock.send.assert_called_once()
    args = mail_mock.send.call_args[0]
    assert args[0] == ["admin@example.com"]
    assert "terminated" in args[1].lower()


@inline_callbacks_test
def test_integration_warning_with_email_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    """When memory exceeds the warning threshold and MEMUSAGE_NOTIFY_MAIL is set,
    a warning email is sent."""
    settings = _base_settings(
        MEMUSAGE_WARNING_MB=50,
        MEMUSAGE_LIMIT_MB=0,
        MEMUSAGE_CHECK_INTERVAL_SECONDS=0.01,
        MEMUSAGE_NOTIFY_MAIL=["admin@example.com"],
    )

    monkeypatch.setattr(
        MemoryUsage, "engine_started", _engine_started_once, raising=True
    )
    monkeypatch.setattr(
        MemoryUsage, "get_virtual_size", lambda self: 75 * MB, raising=True
    )

    mail_mock = MagicMock()
    original_init = MemoryUsage.__init__

    def patched_init(self: MemoryUsage, crawler_arg: Any) -> None:
        original_init(self, crawler_arg)
        self.mail = mail_mock

    monkeypatch.setattr(MemoryUsage, "__init__", patched_init, raising=True)

    crawler = get_crawler(spidercls=_DummySpider, settings_dict=settings)
    yield crawler.crawl()

    assert crawler.stats.get_value("finish_reason") == "finished"
    assert crawler.stats.get_value("memusage/warning_reached") == 1
    assert crawler.stats.get_value("memusage/warning_notified") == 1
    mail_mock.send.assert_called_once()
    args = mail_mock.send.call_args[0]
    assert args[0] == ["admin@example.com"]
    assert "warning" in args[1].lower()


@inline_callbacks_test
def test_integration_no_limit_no_warning_finishes_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    """When no limit or warning is configured, the spider finishes normally."""
    settings = _base_settings(
        MEMUSAGE_LIMIT_MB=0,
        MEMUSAGE_WARNING_MB=0,
        MEMUSAGE_CHECK_INTERVAL_SECONDS=0.01,
    )

    monkeypatch.setattr(
        MemoryUsage, "engine_started", _engine_started_once, raising=True
    )
    monkeypatch.setattr(
        MemoryUsage, "get_virtual_size", lambda self: 50 * MB, raising=True
    )

    crawler = get_crawler(spidercls=_DummySpider, settings_dict=settings)
    yield crawler.crawl()

    assert crawler.stats.get_value("finish_reason") == "finished"
    assert crawler.stats.get_value("memusage/limit_reached") is None
    assert crawler.stats.get_value("memusage/warning_reached") is None
