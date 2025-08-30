"""
Scrapy extension for collecting scraping stats
"""

from __future__ import annotations

import inspect
import logging
import pprint
import warnings
from typing import TYPE_CHECKING, Any

from scrapy.exceptions import ScrapyDeprecationWarning

if TYPE_CHECKING:
    from scrapy import Spider
    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)


StatsT = dict[str, Any]


class StatsCollector:
    def __init__(self, crawler: Crawler):
        self._dump: bool = crawler.settings.getbool("STATS_DUMP")
        self._stats: StatsT = {}
        self._crawler: Crawler = crawler

    def __getattribute__(self, name):
        original_attr = super().__getattribute__(name)

        if name in (
            "get_value",
            "get_stats",
            "set_value",
            "set_stats",
            "inc_value",
            "max_value",
            "min_value",
            "clear_stats",
            "open_spider",
            "close_spider",
        ) and callable(original_attr):

            def _deprecated_wrapper(*args, **kwargs):
                sig = inspect.signature(original_attr).bind(*args, **kwargs)
                sig.apply_defaults()

                if sig.arguments.get("spider"):
                    warnings.warn(
                        f"Passing a 'spider' argument to StatsCollector.{name}() is deprecated and"
                        f" the argument will be removed in a future Scrapy version.",
                        category=ScrapyDeprecationWarning,
                        stacklevel=2,
                    )

                return original_attr(*args, **kwargs)

            return _deprecated_wrapper

        return original_attr

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

    def open_spider(self, spider: Spider | None = None) -> None:
        pass

    def close_spider(
        self, spider: Spider | None = None, reason: str | None = None
    ) -> None:
        if self._dump:
            logger.info(
                "Dumping Scrapy stats:\n" + pprint.pformat(self._stats),
                extra={"spider": self._crawler.spider},
            )
        self._persist_stats(self._stats)

    def _persist_stats(self, stats: StatsT) -> None:
        pass


class MemoryStatsCollector(StatsCollector):
    def __init__(self, crawler: Crawler):
        super().__init__(crawler)
        self.spider_stats: dict[str, StatsT] = {}

    def _persist_stats(self, stats: StatsT) -> None:
        if self._crawler.spider:
            self.spider_stats[self._crawler.spider.name] = stats


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
