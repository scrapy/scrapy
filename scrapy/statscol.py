"""
Scrapy extension for collecting scraping stats
"""
import pprint

from scrapy import log

class StatsCollector(object):

    def __init__(self, crawler):
        self._dump = crawler.settings.getbool('STATS_DUMP')
        self._stats = {}

    def get_value(self, key, default=None, spider=None):
        if spider:
            return self._stats[spider].get(key, default)

    def get_stats(self, spider=None):
        if spider:
            if spider in self._stats:
                return self._stats[spider]
            else:
                return {}
        return self._stats  # maybe sum should be done here

    def set_value(self, key, value, spider=None):
        if spider:
            sp = spider.name
            if sp not in self._stats:
                self._stats[sp] = {}
            self._stats[sp][key] = value

    def set_stats(self, stats, spider=None):
        self._stats = stats

    def inc_value(self, key, count=1, start=0, spider=None):
        if spider:
            sp = spider.name
            if sp not in self._stats:
                self._stats[sp] = {}
            d = self._stats[sp]
            d[key] = d.setdefault(key, start) + count

    def max_value(self, key, value, spider=None):
        if spider:
            sp = spider.name
            if sp not in self._stats:
                self._stats[sp] = {}
            self._stats[sp][key] = max(self._stats[spider].setdefault(key, value), value)

    def min_value(self, key, value, spider=None):
        if spider:
            sp = spider.name
            if sp not in self._stats:
                self._stats[sp] = {}
            self._stats[sp][key] = min(self._stats[spider].setdefault(key, value), value)

    def clear_stats(self, spider=None):
        if spider:
            sp = spider.name
            if sp not in self._stats:
                self._stats[sp] = {}
            self._stats[sp].clear()
        else:
            self._stats.clear()

    def open_spider(self, spider):
        pass

    def close_spider(self, spider, reason):
        if self._dump:
            log.msg("Dumping Scrapy stats:\n" + pprint.pformat(self._stats), \
                spider=spider)
        self._persist_stats(self._stats, spider)

    def _persist_stats(self, stats, spider):
        pass

class MemoryStatsCollector(StatsCollector):

    def __init__(self, crawler):
        super(MemoryStatsCollector, self).__init__(crawler)
        self.spider_stats = {}

    def _persist_stats(self, stats, spider):
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


