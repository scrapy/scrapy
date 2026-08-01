from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import pytest

from scrapy import signals
from scrapy.core import engine as engine_mod
from scrapy.exceptions import NotConfigured
from scrapy.extensions import memusage as memusage_mod
from scrapy.extensions.memusage import MemoryUsage
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from tests.utils import OneShotLoop
from tests.utils.cmdline import proc
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from tests.mockserver.http import MockServer

# MemoryUsage relies on the stdlib 'resource' module (not available on Windows)
pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="MemoryUsage extension not available on Windows",
)


MB = 1024 * 1024


class TwoShotLoop(OneShotLoop):
    """Like :class:`OneShotLoop`, but runs the check twice."""

    def start(self, interval: float, now: bool = True) -> None:
        super().start(interval, now=now)
        self.func()


class _LoopSpider(Spider):
    name = "loop-data-spider"

    def __init__(self, url: str, loops: int = 60, **kw):
        super().__init__(**kw)
        self.url = url
        self.loops = loops
        self.start_urls = [url]

    def parse(self, response):
        count = response.meta.get("count", 0)
        if count + 1 < self.loops:
            yield response.follow(
                self.url, callback=self.parse, meta={"count": count + 1}
            )


def test_memusage_disabled() -> None:
    settings = {
        "MEMUSAGE_ENABLED": False,
    }
    with pytest.raises(NotConfigured):
        MemoryUsage.from_crawler(get_crawler(settings_dict=settings))


def test_memusage_limit_stops_crawler_without_spider(mockserver: MockServer) -> None:
    # The Scrapy shell starts the engine without opening a spider, so the
    # whole crawler is stopped instead of a spider being closed.
    _, out, err = proc(
        "shell",
        mockserver.url("/text"),
        "-c",
        "response.status",
        "--set",
        "MEMUSAGE_LIMIT_MB=1",
    )
    assert "Memory usage exceeded 1MiB" in err
    assert "200" in out


@coroutine_test
async def test_memusage_below_thresholds_logs_peak(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = {
        "MEMUSAGE_LIMIT_MB": 100,
        "MEMUSAGE_WARNING_MB": 50,
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.01,
        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": "INFO",
    }

    monkeypatch.setattr(memusage_mod, "create_looping_call", OneShotLoop)
    monkeypatch.setattr(MemoryUsage, "get_virtual_size", lambda _: 25 * MB)

    crawler = get_crawler(spidercls=_LoopSpider, settings_dict=settings)

    with caplog.at_level(logging.INFO, logger="scrapy.extensions.memusage"):
        await crawler.crawl_async(url="data:,", loops=1)

    assert crawler.stats
    assert crawler.stats.get_value("memusage/limit_reached") is None
    assert crawler.stats.get_value("memusage/warning_reached") is None
    assert crawler.stats.get_value("memusage/max") == 25 * MB
    assert crawler.stats.get_value("finish_reason") == "finished"
    assert any("Peak memory usage is 25MiB" in r.getMessage() for r in caplog.records)


@coroutine_test
async def test_memusage_limit_closes_spider_with_reason_and_error_log(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = {
        "MEMUSAGE_LIMIT_MB": 10,
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.01,
        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": "INFO",
    }

    # Avoid background LoopingCall that can log after the test finishes.
    monkeypatch.setattr(memusage_mod, "create_looping_call", OneShotLoop)
    # Avoid engine start/stop races (the extension stops the engine in engine_started).
    monkeypatch.setattr(engine_mod, "create_looping_call", OneShotLoop)
    monkeypatch.setattr(MemoryUsage, "get_virtual_size", lambda _: 250 * MB)

    crawler = get_crawler(spidercls=_LoopSpider, settings_dict=settings)

    with caplog.at_level(logging.ERROR, logger="scrapy.extensions.memusage"):
        await crawler.crawl_async(url="data:,", loops=100)

    assert crawler.stats
    assert crawler.stats.get_value("memusage/limit_reached") == 1
    assert crawler.stats.get_value("finish_reason") == "memusage_exceeded"
    assert any(
        "memory usage exceeded" in r.getMessage().lower() for r in caplog.records
    )


@coroutine_test
async def test_memusage_warning_logs_but_allows_normal_finish(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = {
        "MEMUSAGE_WARNING_MB": 50,
        "MEMUSAGE_LIMIT_MB": 0,  # no hard limit
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.01,
        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": "INFO",
    }

    # Avoid background LoopingCall that can log after the test finishes; check
    # twice, since the warning is only meant to be reported once.
    monkeypatch.setattr(memusage_mod, "create_looping_call", TwoShotLoop)
    monkeypatch.setattr(MemoryUsage, "get_virtual_size", lambda self: 75 * MB)

    crawler = get_crawler(spidercls=_LoopSpider, settings_dict=settings)

    warning_signals: list[int] = []

    def on_warning_reached() -> None:
        warning_signals.append(1)

    crawler.signals.connect(on_warning_reached, signal=signals.memusage_warning_reached)

    with caplog.at_level(logging.WARNING, logger="scrapy.extensions.memusage"):
        await crawler.crawl_async(url="data:,", loops=60)

    assert warning_signals == [1]
    assert crawler.stats
    assert crawler.stats.get_value("memusage/warning_reached") == 1
    assert crawler.stats.get_value("finish_reason") == "finished"
    warnings_logged = [
        r for r in caplog.records if "memory usage reached" in r.getMessage().lower()
    ]
    assert len(warnings_logged) == 1
