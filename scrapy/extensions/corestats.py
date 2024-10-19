"""
Extension for collecting core stats like items scraped and start/finish times
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from scrapy import Spider, signals

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


class CoreStats:
    def __init__(self, stats: StatsCollector):
        self.stats: StatsCollector = stats
        self.start_time: datetime | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        assert crawler.stats
        o = cls(crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(o.item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(o.item_dropped, signal=signals.item_dropped)
        crawler.signals.connect(o.response_received, signal=signals.response_received)
        return o

    def spider_opened(self, spider: Spider) -> None:
        self.start_time = datetime.now(tz=timezone.utc)
        self.stats.set_value("start_time", self.start_time, spider=spider)

    def spider_closed(self, spider: Spider, reason: str) -> None:
        assert self.start_time is not None
        finish_time = datetime.now(tz=timezone.utc)
        elapsed_time = finish_time - self.start_time
        elapsed_time_seconds = elapsed_time.total_seconds()
        self.stats.set_value(
            "elapsed_time_seconds", elapsed_time_seconds, spider=spider
        )
        self.stats.set_value("finish_time", finish_time, spider=spider)
        self.stats.set_value("finish_reason", reason, spider=spider)

    def item_scraped(self, item: Any, spider: Spider) -> None:
        self.stats.inc_value("item_scraped_count", spider=spider)

    def response_received(self, spider: Spider) -> None:
        self.stats.inc_value("response_received_count", spider=spider)

    def item_dropped(self, item: Any, spider: Spider, exception: BaseException) -> None:
        reason = exception.__class__.__name__
        self.stats.inc_value("item_dropped_count", spider=spider)
        self.stats.inc_value(f"item_dropped_reasons_count/{reason}", spider=spider)
