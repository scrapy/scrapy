"""
Scrapy extension for collecting scraping stats
"""
import pprint

from scrapy.xlib.pydispatch import dispatcher

from scrapy.stats.signals import stats_domain_opened, stats_domain_closing, \
    stats_domain_closed
from scrapy.utils.signal import send_catch_log
from scrapy.core import signals
from scrapy import log
from scrapy.conf import settings

class StatsCollector(object):

    def __init__(self):
        self._dump = settings.getbool('STATS_DUMP')
        self._stats = {None: {}} # None is for global stats

    def get_value(self, key, default=None, domain=None):
        return self._stats[domain].get(key, default)

    def get_stats(self, domain=None):
        return self._stats[domain]

    def set_value(self, key, value, domain=None):
        self._stats[domain][key] = value

    def set_stats(self, stats, domain=None):
        self._stats[domain] = stats

    def inc_value(self, key, count=1, start=0, domain=None):
        d = self._stats[domain]
        d[key] = d.setdefault(key, start) + count

    def max_value(self, key, value, domain=None):
        d = self._stats[domain]
        d[key] = max(d.setdefault(key, value), value)

    def min_value(self, key, value, domain=None):
        d = self._stats[domain]
        d[key] = min(d.setdefault(key, value), value)

    def clear_stats(self, domain=None):
        self._stats[domain].clear()

    def list_domains(self):
        return [d for d in self._stats.keys() if d is not None]

    def open_domain(self, domain):
        self._stats[domain] = {}
        send_catch_log(stats_domain_opened, domain=domain)

    def close_domain(self, domain, reason):
        send_catch_log(stats_domain_closing, domain=domain, reason=reason)
        stats = self._stats.pop(domain)
        send_catch_log(stats_domain_closed, domain=domain, reason=reason, \
            domain_stats=stats)
        if self._dump:
            log.msg("Dumping domain stats:\n" + pprint.pformat(stats), \
                domain=domain)

    def engine_stopped(self):
        if self._dump:
            log.msg("Dumping global stats:\n" + pprint.pformat(self.get_stats()))


class MemoryStatsCollector(StatsCollector):

    def __init__(self):
        super(MemoryStatsCollector, self).__init__()
        self.domain_stats = {}
        
    def close_domain(self, domain, reason):
        self.domain_stats[domain] = self._stats[domain]
        super(MemoryStatsCollector, self).close_domain(domain, reason)


class DummyStatsCollector(StatsCollector):

    def get_value(self, key, default=None, domain=None):
        return default

    def set_value(self, key, value, domain=None):
        pass

    def set_stats(self, stats, domain=None):
        pass

    def inc_value(self, key, count=1, start=0, domain=None):
        pass

    def max_value(self, key, value, domain=None):
        pass

    def min_value(self, key, value, domain=None):
        pass


