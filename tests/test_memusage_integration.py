from __future__ import annotations

import logging
import sys

import pytest
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks

from scrapy import signals
from scrapy.extensions.memusage import MemoryUsage
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler

# memusage relies on the stdlib 'resource' module (not available on Windows)
pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="MemoryUsage extension not available on Windows",
)


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


def _engine_started_once(self: MemoryUsage):
    """
    Test-only replacement for MemoryUsage.engine_started:
    run checks once, synchronously; do not schedule periodic LoopingCalls.
    """
    # keep side-effects identical to a single immediate tick
    self.update()
    if self.limit:
        self._check_limit()
    if self.warning:
        self._check_warning()
    return defer.succeed(None)


@inlineCallbacks
def test_memusage_limit_closes_spider_with_reason_and_error_log(caplog, monkeypatch):
    url = "data:,"
    settings = {
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_LIMIT_MB": 10,
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.01,
        "LOG_LEVEL": "INFO",
    }

    # Avoid background timers; run memusage checks once synchronously.
    monkeypatch.setattr(
        MemoryUsage, "engine_started", _engine_started_once, raising=True
    )

    MB = 1024 * 1024
    state = {"high": False}

    def fake_vsz(self):
        return 250 * MB if state["high"] else 5 * MB

    monkeypatch.setattr(MemoryUsage, "get_virtual_size", fake_vsz, raising=True)

    crawler = get_crawler(spidercls=_LoopSpider, settings_dict=settings)

    def on_opened(spider):
        state["high"] = True

    crawler.signals.connect(on_opened, signal=signals.spider_opened)

    caplog.set_level(logging.ERROR, logger="scrapy.extensions.memusage")
    yield crawler.crawl(url=url, loops=100)

    assert crawler.stats.get_value("finish_reason") == "memusage_exceeded"
    assert any(
        "memory usage exceeded" in r.getMessage().lower() for r in caplog.records
    )


@inlineCallbacks
def test_memusage_warning_logs_but_allows_normal_finish(caplog, monkeypatch):
    url = "data:,"
    settings = {
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_WARNING_MB": 50,
        "MEMUSAGE_LIMIT_MB": 0,  # no hard limit
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.01,
        "LOG_LEVEL": "INFO",
    }

    # Avoid background timers; run memusage checks once synchronously.
    monkeypatch.setattr(
        MemoryUsage, "engine_started", _engine_started_once, raising=True
    )

    MB = 1024 * 1024
    monkeypatch.setattr(
        MemoryUsage, "get_virtual_size", lambda self: 75 * MB, raising=True
    )

    crawler = get_crawler(spidercls=_LoopSpider, settings_dict=settings)

    caplog.set_level(logging.WARNING, logger="scrapy.extensions.memusage")
    yield crawler.crawl(url=url, loops=60)

    assert crawler.stats.get_value("finish_reason") == "finished"
    assert any("memory usage reached" in r.getMessage().lower() for r in caplog.records)
