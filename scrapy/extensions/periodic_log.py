from __future__ import annotations

import logging
from datetime import datetime, timezone
from json import JSONEncoder
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from twisted.internet import task

from scrapy import Spider, signals
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.statscollectors import StatsCollector
from scrapy.utils.serialize import ScrapyJSONEncoder

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

logger = logging.getLogger(__name__)


class PeriodicLog:
    """Log basic scraping stats periodically"""

    def __init__(
        self,
        stats: StatsCollector,
        interval: float = 60.0,
        ext_stats: Dict[str, Any] = {},
        ext_delta: Dict[str, Any] = {},
        ext_timing_enabled: bool = False,
    ):
        self.stats: StatsCollector = stats
        self.interval: float = interval
        self.multiplier: float = 60.0 / self.interval
        self.task: Optional[task.LoopingCall] = None
        self.encoder: JSONEncoder = ScrapyJSONEncoder(sort_keys=True, indent=4)
        self.ext_stats_enabled: bool = bool(ext_stats)
        self.ext_stats_include: List[str] = ext_stats.get("include", [])
        self.ext_stats_exclude: List[str] = ext_stats.get("exclude", [])
        self.ext_delta_enabled: bool = bool(ext_delta)
        self.ext_delta_include: List[str] = ext_delta.get("include", [])
        self.ext_delta_exclude: List[str] = ext_delta.get("exclude", [])
        self.ext_timing_enabled: bool = ext_timing_enabled

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        interval: float = crawler.settings.getfloat("LOGSTATS_INTERVAL")
        if not interval:
            raise NotConfigured
        try:
            ext_stats: Optional[Dict[str, Any]] = crawler.settings.getdict(
                "PERIODIC_LOG_STATS"
            )
        except (TypeError, ValueError):
            ext_stats = (
                {"enabled": True}
                if crawler.settings.getbool("PERIODIC_LOG_STATS")
                else None
            )
        try:
            ext_delta: Optional[Dict[str, Any]] = crawler.settings.getdict(
                "PERIODIC_LOG_DELTA"
            )
        except (TypeError, ValueError):
            ext_delta = (
                {"enabled": True}
                if crawler.settings.getbool("PERIODIC_LOG_DELTA")
                else None
            )

        ext_timing_enabled: bool = crawler.settings.getbool(
            "PERIODIC_LOG_TIMING_ENABLED", False
        )
        if not (ext_stats or ext_delta or ext_timing_enabled):
            raise NotConfigured
        assert crawler.stats
        assert ext_stats is not None
        assert ext_delta is not None
        o = cls(
            crawler.stats,
            interval,
            ext_stats,
            ext_delta,
            ext_timing_enabled,
        )
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_opened(self, spider: Spider) -> None:
        self.time_prev: datetime = datetime.now(tz=timezone.utc)
        self.delta_prev: Dict[str, Union[int, float]] = {}
        self.stats_prev: Dict[str, Union[int, float]] = {}

        self.task = task.LoopingCall(self.log)
        self.task.start(self.interval)

    def log(self) -> None:
        data: Dict[str, Any] = {}
        if self.ext_timing_enabled:
            data.update(self.log_timing())
        if self.ext_delta_enabled:
            data.update(self.log_delta())
        if self.ext_stats_enabled:
            data.update(self.log_crawler_stats())
        logger.info(self.encoder.encode(data))

    def log_delta(self) -> Dict[str, Any]:
        num_stats: Dict[str, Union[int, float]] = {
            k: v
            for k, v in self.stats._stats.items()
            if isinstance(v, (int, float))
            and self.param_allowed(k, self.ext_delta_include, self.ext_delta_exclude)
        }
        delta = {k: v - self.delta_prev.get(k, 0) for k, v in num_stats.items()}
        self.delta_prev = num_stats
        return {"delta": delta}

    def log_timing(self) -> Dict[str, Any]:
        now = datetime.now(tz=timezone.utc)
        time = {
            "log_interval": self.interval,
            "start_time": self.stats._stats["start_time"],
            "utcnow": now,
            "log_interval_real": (now - self.time_prev).total_seconds(),
            "elapsed": (now - self.stats._stats["start_time"]).total_seconds(),
        }
        self.time_prev = now
        return {"time": time}

    def log_crawler_stats(self) -> Dict[str, Any]:
        stats = {
            k: v
            for k, v in self.stats._stats.items()
            if self.param_allowed(k, self.ext_stats_include, self.ext_stats_exclude)
        }
        return {"stats": stats}

    def param_allowed(
        self, stat_name: str, include: List[str], exclude: List[str]
    ) -> bool:
        if not include and not exclude:
            return True
        for p in exclude:
            if p in stat_name:
                return False
        if exclude and not include:
            return True
        for p in include:
            if p in stat_name:
                return True
        return False

    def spider_closed(self, spider: Spider, reason: str) -> None:
        self.log()
        if self.task and self.task.running:
            self.task.stop()
