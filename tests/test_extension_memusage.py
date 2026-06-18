from __future__ import annotations

import logging
import sys

import pytest

from scrapy.extensions import memusage as memusage_mod
from scrapy.extensions.memusage import MemoryUsage
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from tests.utils import OneShotLoop
from tests.utils.decorators import coroutine_test

# MemoryUsage relies on the stdlib 'resource' module (not available on Windows)
pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="MemoryUsage extension not available on Windows",
)


MB = 1024 * 1024


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


@coroutine_test
async def test_memusage_limit_closes_spider_with_reason_and_error_log(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = {
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_LIMIT_MB": 10,
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.01,
        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": "INFO",
    }

    # Avoid background LoopingCall that can log after the test finishes.
    monkeypatch.setattr(memusage_mod, "create_looping_call", OneShotLoop)
    monkeypatch.setattr(MemoryUsage, "get_virtual_size", lambda _: 250 * MB)

    crawler = get_crawler(spidercls=_LoopSpider, settings_dict=settings)

    with caplog.at_level(logging.ERROR, logger="scrapy.extensions.memusage"):
        await crawler.crawl_async(url="data:,", loops=100)

    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == "memusage_exceeded"
    assert any(
        "memory usage exceeded" in r.getMessage().lower() for r in caplog.records
    )


@coroutine_test
async def test_memusage_warning_logs_but_allows_normal_finish(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = {
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_WARNING_MB": 50,
        "MEMUSAGE_LIMIT_MB": 0,  # no hard limit
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 0.01,
        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": "INFO",
    }

    # Avoid background LoopingCall that can log after the test finishes.
    monkeypatch.setattr(memusage_mod, "create_looping_call", OneShotLoop)
    monkeypatch.setattr(MemoryUsage, "get_virtual_size", lambda self: 75 * MB)

    crawler = get_crawler(spidercls=_LoopSpider, settings_dict=settings)

    with caplog.at_level(logging.WARNING, logger="scrapy.extensions.memusage"):
        await crawler.crawl_async(url="data:,", loops=60)

    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == "finished"
    assert any("memory usage reached" in r.getMessage().lower() for r in caplog.records)
