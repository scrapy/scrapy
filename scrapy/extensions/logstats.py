from datetime import datetime
import logging

from twisted.internet import task

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.serialize import ScrapyJSONEncoder

logger = logging.getLogger(__name__)


class LogStats:
    """Log basic scraping stats periodically"""

    def __init__(self, stats, interval=60.0, extended=False, ext_include=None, ext_exclude=None):
        self.stats = stats
        self.interval = interval
        self.multiplier = 60.0 / self.interval
        self.task = None
        self.extended = extended
        if self.extended:
            self.encoder = ScrapyJSONEncoder(sort_keys=True, indent=4)
        self.ext_include = ext_include
        self.ext_exclude = ext_exclude

    @classmethod
    def from_crawler(cls, crawler):
        interval = crawler.settings.getfloat("LOGSTATS_INTERVAL")
        extended = crawler.settings.getbool("LOGSTATS_EXTENDED_ENABLED")
        ext_include = crawler.settings.getlist("LOGSTATS_EXTENDED_INCLUDE", [])
        ext_exclude = crawler.settings.getlist("LOGSTATS_EXTENDED_EXCLUDE", [])
        if not interval:
            raise NotConfigured
        o = cls(crawler.stats, interval, extended, ext_include, ext_exclude)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_opened(self, spider):
        self.pagesprev = 0
        self.itemsprev = 0
        if self.extended:
            self.time_prev = datetime.utcnow()
            self.delta_prev = {}
            self.stats_prev = {}

        self.task = task.LoopingCall(self.log, spider)
        self.task.start(self.interval)

    def log(self, spider):
        if self.extended:
            data = {}
            data.update(self.log_timing())
            data.update(self.log_delta())
            data.update(self.log_crawler_stats())
            logger.info(
                self.encoder.encode(data)
            )
        else:
            items = self.stats.get_value("item_scraped_count", 0)
            pages = self.stats.get_value("response_received_count", 0)
            irate = (items - self.itemsprev) * self.multiplier
            prate = (pages - self.pagesprev) * self.multiplier
            self.pagesprev, self.itemsprev = pages, items

            msg = (
                "Crawled %(pages)d pages (at %(pagerate)d pages/min), "
                "scraped %(items)d items (at %(itemrate)d items/min)"
            )
            log_args = {
                "pages": pages,
                "pagerate": prate,
                "items": items,
                "itemrate": irate,
            }
            logger.info(msg, log_args, extra={"spider": spider})

    def log_delta(self):
        num_stats = {
            k: v for k, v in self.stats._stats.items()
            if isinstance(v, (int, float)) and self.delta_param_allowed(k)
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
            "elapsed": (now - self.stats._stats["start_time"]).total_seconds()}
        self.time_prev = now
        return {"time": time}

    def log_time(self):
        num_stats = {
            k: v for k, v in self.stats._stats.items()
            if isinstance(v, (int, float)) and self.delta_param_allowed(k)
        }
        delta = {k: v - self.stats_prev.get(k, 0) for k, v in num_stats.items()}
        self.stats_prev = num_stats
        return {"delta": delta}

    def log_crawler_stats(self):
        return {"stats": self.stats.get_stats()}

    def delta_param_allowed(self, stat_name):
        for p in self.ext_exclude:
            if p in stat_name:
                return False
        for p in self.ext_include:
            if p in stat_name:
                return True
        if self.ext_include:
            return False
        else:
            return True

    def spider_closed(self, spider, reason):
        if self.extended:
            data = {}
            data.update(self.log_timing())
            data.update(self.log_delta())
            data.update(self.log_crawler_stats())
            logger.info(
                self.encoder.encode(data)
            )
        if self.task and self.task.running:
            self.task.stop()
