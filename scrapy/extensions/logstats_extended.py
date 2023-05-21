import logging
from datetime import datetime

from twisted.internet import task

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.serialize import ScrapyJSONEncoder

logger = logging.getLogger(__name__)


class LogStatsExtended:
    """Log basic scraping stats periodically"""

    def __init__(
            self, stats, interval=60.0,
            ext_stats_enabled=False,
            ext_stats_include=None,
            ext_stats_exclude=None,
            ext_delta_enabled=False,
            ext_delta_include=None,
            ext_delta_exclude=None,
            ext_timing_enabled=False,
            ext_timing_include=None,
            ext_timing_exclude=None,
    ):
        self.stats = stats
        self.interval = interval
        self.multiplier = 60.0 / self.interval
        self.task = None
        self.encoder = ScrapyJSONEncoder(sort_keys=True, indent=4)
        self.ext_stats_enabled = ext_stats_enabled
        self.ext_stats_include = ext_stats_include
        self.ext_stats_exclude = ext_stats_exclude
        self.ext_delta_enabled = ext_delta_enabled
        self.ext_delta_include = ext_delta_include
        self.ext_delta_exclude = ext_delta_exclude
        self.ext_timing_enabled = ext_timing_enabled
        self.ext_timing_include = ext_timing_include
        self.ext_timing_exclude = ext_timing_exclude


    @classmethod
    def from_crawler(cls, crawler):
        interval = crawler.settings.getfloat("LOGSTATS_INTERVAL")
        ext_stats_enabled = crawler.settings.getbool("LOGSTATS_EXT_STATS_ENABLED")
        ext_stats_include = crawler.settings.getlist("LOGSTATS_EXT_STATS_INCLUDE", [])
        ext_stats_exclude = crawler.settings.getlist("LOGSTATS_EXT_STATS_EXCLUDE", [])
        ext_delta_enabled = crawler.settings.getbool("LOGSTATS_EXT_DELTA_ENABLED")
        ext_delta_include = crawler.settings.getlist("LOGSTATS_EXT_DELTA_INCLUDE", [])
        ext_delta_exclude = crawler.settings.getlist("LOGSTATS_EXT_DELTA_EXCLUDE", [])
        ext_timing_enabled = crawler.settings.getbool("LOGSTATS_EXT_TIMING_ENABLED")
        if not interval:
            raise NotConfigured
        if not (ext_stats_enabled or ext_delta_enabled or ext_timing_enabled):
            raise NotConfigured
        o = cls(crawler.stats,
                interval,
                ext_stats_enabled,
                ext_stats_include,
                ext_stats_exclude,
                ext_delta_enabled,
                ext_delta_include,
                ext_delta_exclude,
                ext_timing_enabled,
               )
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_opened(self, spider):
        self.time_prev = datetime.utcnow()
        self.delta_prev = {}
        self.stats_prev = {}

        self.task = task.LoopingCall(self.log, spider)
        self.task.start(self.interval)

    def log(self, spider):
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
            if isinstance(v, (int, float)) and self.param_allowed(k,self.ext_delta_include,self.ext_delta_exclude)
        }
        delta = {k: v - self.delta_prev.get(k, 0) for k, v in num_stats.items()}
        self.delta_prev = num_stats
        return {"delta": delta}

    def log_timing(self):
        now = datetime.utcnow()
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
            if self.param_allowed(k,self.ext_stats_include, self.ext_stats_exclude)}
        return {"stats": stats}

    def param_allowed(self, stat_name, include, exclude):
        for p in exclude:
            if p in stat_name:
                return False
        for p in include:
            if p in stat_name:
                return True
        return False


    def spider_closed(self, spider, reason):
        self.log(spider)
        if self.task and self.task.running:
            self.task.stop()
