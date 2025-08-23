from __future__ import annotations

import logging
import sys

import pytest
from twisted.internet.defer import inlineCallbacks

from scrapy import signals
from scrapy.extensions.memusage import MemoryUsage
from scrapy.settings import Settings
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler

# memusage relies on the stdlib 'resource' module (not available on Windows)
pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="MemoryUsage extension not available on Windows",
)

MiB = 1024 * 1024


def _installed_reactor_path() -> str:
    """Return the fully qualified path of the *already installed* Twisted reactor.
    Local import avoids module-level reactor import (keeps Ruff happy)."""
    from twisted.internet import reactor as _reactor  # local on purpose

    cls = _reactor.__class__
    return f"{cls.__module__}.{cls.__name__}"


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


@inlineCallbacks
def test_memusage_limit_closes_spider_with_reason_and_error_log(caplog, monkeypatch):
    url = "data:,"
    settings = Settings(
        {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 10,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.01,
            "LOG_LEVEL": "INFO",
        }
    )
    # Respect the reactor already installed by the test env/CI.
    settings.set("TWISTED_REACTOR", _installed_reactor_path(), priority="cmdline")

    state = {"high": False}

    def fake_vsz(self):
        return 250 * MiB if state["high"] else 5 * MiB

    monkeypatch.setattr(MemoryUsage, "get_virtual_size", fake_vsz)

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
    settings = Settings(
        {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 50,
            "MEMUSAGE_LIMIT_MB": 0,  # no hard limit
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.01,
            "LOG_LEVEL": "INFO",
        }
    )
    # Respect the reactor already installed by the test env/CI.
    settings.set("TWISTED_REACTOR", _installed_reactor_path(), priority="cmdline")

    monkeypatch.setattr(MemoryUsage, "get_virtual_size", lambda self: 75 * MiB)

    crawler = get_crawler(spidercls=_LoopSpider, settings_dict=settings)

    caplog.set_level(logging.WARNING, logger="scrapy.extensions.memusage")
    yield crawler.crawl(url=url, loops=60)

    assert crawler.stats.get_value("finish_reason") == "finished"
    assert any("memory usage reached" in r.getMessage().lower() for r in caplog.records)
