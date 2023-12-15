import logging
from datetime import datetime, timezone

from twisted.internet import task

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.serialize import ScrapyJSONEncoder

logger = logging.getLogger(__name__)


class PeriodicLog:
    """Log basic scraping stats periodically"""

    def __init__(
        self,
        stats,
        interval=60.0,
        ext_stats={},
        ext_delta={},
        ext_timing_enabled=False,
    ):
        self.stats = stats
        self.interval = interval
        self.multiplier = 60.0 / self.interval
        self.task = None
        self.encoder = ScrapyJSONEncoder(sort_keys=True, indent=4)
        self.ext_stats_enabled = bool(ext_stats)
        self.ext_stats_include = ext_stats.get("include", [])
        self.ext_stats_exclude = ext_stats.get("exclude", [])
        self.ext_delta_enabled = bool(ext_delta)
        self.ext_delta_include = ext_delta.get("include", [])
        self.ext_delta_exclude = ext_delta.get("exclude", [])
        self.ext_timing_enabled = ext_timing_enabled

    @classmethod
    def from_crawler(cls, crawler):
        interval = crawler.settings.getfloat("LOGSTATS_INTERVAL")
        if not interval:
            raise NotConfigured
        try:
            ext_stats = crawler.settings.getdict("PERIODIC_LOG_STATS")
        except (TypeError, ValueError):
            ext_stats = (
                {"enabled": True}
                if crawler.settings.getbool("PERIODIC_LOG_STATS")
                else None
            )
        try:
            ext_delta = crawler.settings.getdict("PERIODIC_LOG_DELTA")
        except (TypeError, ValueError):
            ext_delta = (
                {"enabled": True}
                if crawler.settings.getbool("PERIODIC_LOG_DELTA")
                else None
            )

        ext_timing_enabled = crawler.settings.getbool(
            "PERIODIC_LOG_TIMING_ENABLED", False
        )
        if not (ext_stats or ext_delta or ext_timing_enabled):
            raise NotConfigured
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

    def spider_opened(self, spider):
        self.time_prev = datetime.now(tz=timezone.utc)
        self.delta_prev = {}
        self.stats_prev = {}

        self.task = task.LoopingCall(self.log)
        self.task.start(self.interval)

    def log(self):
        data = {}
        if self.ext_timing_enabled:
            data.update(self.log_timing())
        if self.ext_delta_enabled:
            data.update(self.log_delta())
        if self.ext_stats_enabled:
            data.update(self.log_crawler_stats())
        logger.info(self.encoder.encode(data))

    def log_delta(self):
        num_stats = {
            k: v
            for k, v in self.stats._stats.items()
            if isinstance(v, (int, float))
            and self.param_allowed(k, self.ext_delta_include, self.ext_delta_exclude)
        }
        delta = {k: v - self.delta_prev.get(k, 0) for k, v in num_stats.items()}
        self.delta_prev = num_stats
        return {"delta": delta}

    def log_timing(self):
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

    def log_crawler_stats(self):
        stats = {
            k: v
            for k, v in self.stats._stats.items()
            if self.param_allowed(k, self.ext_stats_include, self.ext_stats_exclude)
        }
        return {"stats": stats}

    def param_allowed(self, stat_name, include, exclude):
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

    def spider_closed(self, spider, reason):
        self.log()
        if self.task and self.task.running:
            self.task.stop()
