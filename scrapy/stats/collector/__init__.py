"""
Scrapy extension for collecting scraping stats
"""
import pprint

from scrapy.xlib.pydispatch import dispatcher

from scrapy.stats.signals import stats_domain_opened, stats_domain_closing, \
    stats_domain_closed
from scrapy.core import signals
from scrapy import log
from scrapy.conf import settings

class StatsCollector(object):

    def __init__(self):
        self._dump = settings.getbool('STATS_DUMP')
        self._stats = {None: {}} # None is for global stats

        dispatcher.connect(self.open_domain, signal=signals.domain_open)
        dispatcher.connect(self._start_closing_domain, signal=signals.domain_closed)
        dispatcher.connect(self.engine_stopped, signal=signals.engine_stopped)

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

    def clear_stats(self, domain=None):
        self._stats[domain].clear()

    def list_domains(self):
        return [d for d in self._stats.keys() if d is not None]

    def open_domain(self, domain):
        self._stats[domain] = {}
        signals.send_catch_log(stats_domain_opened, domain=domain)

    def close_domain(self, domain, reason):
        if self._dump:
            log.msg("Dumping stats:\n" + pprint.pformat(self.get_stats(domain)), \
                domain=domain)
        del self._stats[domain]
        signals.send_catch_log(stats_domain_closed, domain=domain, reason=reason)

    def engine_stopped(self):
        if self._dump:
            log.msg("Dumping global stats:\n" + pprint.pformat(self.get_stats()))

    def _start_closing_domain(self, domain, reason):
        signals.send_catch_log(stats_domain_closing, domain=domain, reason=reason)
        self.close_domain(domain, reason)

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
