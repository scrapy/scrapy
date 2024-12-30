"""
Scrapy extension for collecting scraping stats
"""

from __future__ import annotations

import logging
import pprint
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scrapy import Spider
    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)


StatsT = dict[str, Any]


class StatsCollector:
    def __init__(self, crawler: Crawler):
        self._dump: bool = crawler.settings.getbool("STATS_DUMP")
        self._stats: StatsT = {}

    def get_value(
        self, key: str, default: Any = None, spider: Spider | None = None
    ) -> Any:
        return self._stats.get(key, default)

    def get_stats(self, spider: Spider | None = None) -> StatsT:
        return self._stats

    def set_value(self, key: str, value: Any, spider: Spider | None = None) -> None:
        self._stats[key] = value

    def set_stats(self, stats: StatsT, spider: Spider | None = None) -> None:
        self._stats = stats

    def inc_value(
        self, key: str, count: int = 1, start: int = 0, spider: Spider | None = None
    ) -> None:
        d = self._stats
        d[key] = d.setdefault(key, start) + count

    def max_value(self, key: str, value: Any, spider: Spider | None = None) -> None:
        self._stats[key] = max(self._stats.setdefault(key, value), value)

    def min_value(self, key: str, value: Any, spider: Spider | None = None) -> None:
        self._stats[key] = min(self._stats.setdefault(key, value), value)

    def clear_stats(self, spider: Spider | None = None) -> None:
        self._stats.clear()

    def open_spider(self, spider: Spider) -> None:
        pass

    def close_spider(self, spider: Spider, reason: str) -> None:
        if self._dump:
            logger.info(
                "Dumping Scrapy stats:\n" + pprint.pformat(self._stats),
                extra={"spider": spider},
            )
        self._persist_stats(self._stats, spider)

    def _persist_stats(self, stats: StatsT, spider: Spider) -> None:
        pass


class MemoryStatsCollector(StatsCollector):
    def __init__(self, crawler: Crawler):
        super().__init__(crawler)
        self.spider_stats: dict[str, StatsT] = {}

    def _persist_stats(self, stats: StatsT, spider: Spider) -> None:
        self.spider_stats[spider.name] = stats


class DummyStatsCollector(StatsCollector):
    def get_value(
        self, key: str, default: Any = None, spider: Spider | None = None
    ) -> Any:
        return default

    def set_value(self, key: str, value: Any, spider: Spider | None = None) -> None:
        pass

    def set_stats(self, stats: StatsT, spider: Spider | None = None) -> None:
        pass

    def inc_value(
        self, key: str, count: int = 1, start: int = 0, spider: Spider | None = None
    ) -> None:
        pass

    def max_value(self, key: str, value: Any, spider: Spider | None = None) -> None:
        pass

    def min_value(self, key: str, value: Any, spider: Spider | None = None) -> None:
        pass
