from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from twisted.internet.defer import inlineCallbacks

from scrapy import signals
from scrapy.crawler import CrawlerRunner
from scrapy.extensions.memusage import MemoryUsage
from scrapy.settings import Settings
from scrapy.spiders import Spider

# Memusage relies on 'resource' (Unix only).
pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="MemoryUsage extension not available on Windows",
)


class _LoopSpider(Spider):
    """Keeps the engine running long enough for periodic checks."""

    name = "loop-file-spider"

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


def _tmp_file_uri(tmp_path: Path) -> str:
    f = tmp_path / "hello.txt"
    f.write_text("hello\n")
    return f.as_uri()


def _pin_reactor_to_installed(settings: Settings) -> None:
    """Honor the reactor already installed by the test env/CI."""
    from twisted.internet import (
        reactor as _reactor,  # local import to avoid import-time issues
    )

    settings.set(
        "TWISTED_REACTOR",
        f"{_reactor.__class__.__module__}.{_reactor.__class__.__name__}",
        priority="cmdline",
    )


@inlineCallbacks
@pytest.mark.twisted
def test_memusage_limit_closes_spider_with_reason_and_error_log(
    tmp_path, caplog, monkeypatch
):
    url = _tmp_file_uri(tmp_path)
    settings = Settings(
        {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 10,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.01,
            "LOG_LEVEL": "INFO",
        }
    )
    _pin_reactor_to_installed(settings)

    MB = 1024 * 1024
    state = {"high": False}

    def fake_vsz(self):
        return 250 * MB if state["high"] else 5 * MB

    monkeypatch.setattr(MemoryUsage, "get_virtual_size", fake_vsz)

    runner = CrawlerRunner(settings)
    crawler = runner.create_crawler(_LoopSpider)

    def on_opened(spider):
        state["high"] = True

    crawler.signals.connect(on_opened, signal=signals.spider_opened)

    caplog.set_level(logging.ERROR, logger="scrapy.extensions.memusage")
    yield runner.crawl(crawler, url=url, loops=100)

    assert crawler.stats.get_value("finish_reason") == "memusage_exceeded"
    assert any(
        "memory usage exceeded" in r.getMessage().lower() for r in caplog.records
    )


@inlineCallbacks
@pytest.mark.twisted
def test_memusage_warning_logs_but_allows_normal_finish(tmp_path, caplog, monkeypatch):
    url = _tmp_file_uri(tmp_path)
    settings = Settings(
        {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_WARNING_MB": 50,
            "MEMUSAGE_LIMIT_MB": 0,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.01,
            "LOG_LEVEL": "INFO",
        }
    )
    _pin_reactor_to_installed(settings)

    MB = 1024 * 1024
    monkeypatch.setattr(MemoryUsage, "get_virtual_size", lambda self: 75 * MB)

    runner = CrawlerRunner(settings)
    crawler = runner.create_crawler(_LoopSpider)

    caplog.set_level(logging.WARNING, logger="scrapy.extensions.memusage")
    yield runner.crawl(crawler, url=url, loops=60)

    assert crawler.stats.get_value("finish_reason") == "finished"
    assert any(
        ("memory usage reached" in r.getMessage().lower())
        or ("memory usage warning" in r.getMessage().lower())
        or ("warning: memory usage reached" in r.getMessage().lower())
        for r in caplog.records
    )
