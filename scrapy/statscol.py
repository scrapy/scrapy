"""
Scrapy extension for collecting scraping stats
"""
import pprint

from scrapy.xlib.pydispatch import dispatcher

from scrapy.signals import stats_spider_opened, stats_spider_closing, \
    stats_spider_closed
from scrapy.utils.signal import send_catch_log
from scrapy import signals
from scrapy import log
from scrapy.conf import settings

class StatsCollector(object):

    def __init__(self):
        self._dump = settings.getbool('STATS_DUMP')
        self._stats = {None: {}} # None is for global stats

    def get_value(self, key, default=None, spider=None):
        return self._stats[spider].get(key, default)

    def get_stats(self, spider=None):
        return self._stats[spider]

    def set_value(self, key, value, spider=None):
        self._stats[spider][key] = value

    def set_stats(self, stats, spider=None):
        self._stats[spider] = stats

    def inc_value(self, key, count=1, start=0, spider=None):
        d = self._stats[spider]
        d[key] = d.setdefault(key, start) + count

    def max_value(self, key, value, spider=None):
        d = self._stats[spider]
        d[key] = max(d.setdefault(key, value), value)

    def min_value(self, key, value, spider=None):
        d = self._stats[spider]
        d[key] = min(d.setdefault(key, value), value)

    def clear_stats(self, spider=None):
        self._stats[spider].clear()

    def iter_spider_stats(self):
        return [x for x in self._stats.iteritems() if x[0]]

    def open_spider(self, spider):
        self._stats[spider] = {}
        send_catch_log(stats_spider_opened, spider=spider)

    def close_spider(self, spider, reason):
        send_catch_log(stats_spider_closing, spider=spider, reason=reason)
        stats = self._stats.pop(spider)
        send_catch_log(stats_spider_closed, spider=spider, reason=reason, \
            spider_stats=stats)
        if self._dump:
            log.msg("Dumping spider stats:\n" + pprint.pformat(stats), \
                spider=spider)
        self._persist_stats(stats, spider)

    def engine_stopped(self):
        stats = self.get_stats()
        if self._dump:
            log.msg("Dumping global stats:\n" + pprint.pformat(stats))
        self._persist_stats(stats, spider=None)

    def _persist_stats(self, stats, spider=None):
        pass

class MemoryStatsCollector(StatsCollector):

    def __init__(self):
        super(MemoryStatsCollector, self).__init__()
        self.spider_stats = {}

    def _persist_stats(self, stats, spider=None):
        if spider is not None:
            self.spider_stats[spider.name] = stats


class DummyStatsCollector(StatsCollector):

    def get_value(self, key, default=None, spider=None):
        return default

    def set_value(self, key, value, spider=None):
        pass

    def set_stats(self, stats, spider=None):
        pass

    def inc_value(self, key, count=1, start=0, spider=None):
        pass

    def max_value(self, key, value, spider=None):
        pass

    def min_value(self, key, value, spider=None):
        pass


