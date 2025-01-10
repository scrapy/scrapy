from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from twisted.internet import task

from scrapy import Spider, signals
from scrapy.exceptions import NotConfigured

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


logger = logging.getLogger(__name__)


class LogStats:
    """Log basic scraping stats periodically like:
    * RPM - Requests per Minute
    * IPM - Items per Minute
    """

    def __init__(self, stats: StatsCollector, interval: float = 60.0):
        self.stats: StatsCollector = stats
        self.interval: float = interval
        self.multiplier: float = 60.0 / self.interval
        self.task: task.LoopingCall | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        interval: float = crawler.settings.getfloat("LOGSTATS_INTERVAL")
        if not interval:
            raise NotConfigured
        assert crawler.stats
        o = cls(crawler.stats, interval)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_opened(self, spider: Spider) -> None:
        self.pagesprev: int = 0
        self.itemsprev: int = 0

        self.task = task.LoopingCall(self.log, spider)
        self.task.start(self.interval)

    def log(self, spider: Spider) -> None:
        self.calculate_stats()

        msg = (
            "Crawled %(pages)d pages (at %(pagerate)d pages/min), "
            "scraped %(items)d items (at %(itemrate)d items/min)"
        )
        log_args = {
            "pages": self.pages,
            "pagerate": self.prate,
            "items": self.items,
            "itemrate": self.irate,
        }
        logger.info(msg, log_args, extra={"spider": spider})

    def calculate_stats(self) -> None:
        self.items: int = self.stats.get_value("item_scraped_count", 0)
        self.pages: int = self.stats.get_value("response_received_count", 0)
        self.irate: float = (self.items - self.itemsprev) * self.multiplier
        self.prate: float = (self.pages - self.pagesprev) * self.multiplier
        self.pagesprev, self.itemsprev = self.pages, self.items

    def spider_closed(self, spider: Spider, reason: str) -> None:
        if self.task and self.task.running:
            self.task.stop()

        rpm_final, ipm_final = self.calculate_final_stats(spider)
        self.stats.set_value("responses_per_minute", rpm_final)
        self.stats.set_value("items_per_minute", ipm_final)

    def calculate_final_stats(
        self, spider: Spider
    ) -> tuple[None, None] | tuple[float, float]:
        start_time = self.stats.get_value("start_time")
        finish_time = self.stats.get_value("finish_time")

        if not start_time or not finish_time:
            return None, None

        mins_elapsed = (finish_time - start_time).seconds / 60

        if mins_elapsed == 0:
            return None, None

        items = self.stats.get_value("item_scraped_count", 0)
        pages = self.stats.get_value("response_received_count", 0)

        return (pages / mins_elapsed), (items / mins_elapsed)
