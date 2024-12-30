"""
MemoryDebugger extension

See documentation in docs/topics/extensions.rst
"""

from __future__ import annotations

import gc
from typing import TYPE_CHECKING

from scrapy import Spider, signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.trackref import live_refs

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


class MemoryDebugger:
    def __init__(self, stats: StatsCollector):
        self.stats: StatsCollector = stats

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if not crawler.settings.getbool("MEMDEBUG_ENABLED"):
            raise NotConfigured
        assert crawler.stats
        o = cls(crawler.stats)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_closed(self, spider: Spider, reason: str) -> None:
        gc.collect()
        self.stats.set_value(
            "memdebug/gc_garbage_count", len(gc.garbage), spider=spider
        )
        for cls, wdict in live_refs.items():
            if not wdict:
                continue
            self.stats.set_value(
                f"memdebug/live_refs/{cls.__name__}", len(wdict), spider=spider
            )
