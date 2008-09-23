"""
Scrapy extension for collecting scraping stats
"""
import pprint

from pydispatch import dispatcher

from scrapy.core import signals
from scrapy import log
from scrapy.utils.misc import stats_getpath
from scrapy.conf import settings

class StatsCollector(dict):
    # signal sent after a domain is opened for stats collection and its resorces have been allocated. args: domain
    domain_open = object()
    # signal sent before a domain is closed, and before the stats are persisted. it can be catched to add additional stats. args: domain
    domain_closing = object()
    # signal sent after a domain is closed and its resources have been freed.  args: domain
    domain_closed = object()

    def __init__(self, enabled=None):
        self.db = None
        self.debug = settings.getbool('STATS_DEBUG')
        self.enabled = enabled if enabled is not None else settings.getbool('STATS_ENABLED')
        self.cleanup = settings.getbool('STATS_CLEANUP')

        if self.enabled:
            if settings['SCRAPING_DB']:
                from scrapy.store.db import DomainDataHistory
                self.db = DomainDataHistory(settings['SCRAPING_DB'], table_name='domain_data_history')

            dispatcher.connect(self._domain_open, signal=signals.domain_open)
            dispatcher.connect(self._domain_closed, signal=signals.domain_closed)
        else:
            self.setpath = lambda *args, **kwargs: None
            self.getpath = lambda path, default=None: default
            self.incpath = lambda *args, **kwargs: None
            self.delpath = lambda *args, **kwargs: None

    def setpath(self, path, value):
        d = self
        keys = path.split('/')
        for key in keys[:-1]:
            if key not in d:
                d[key] = {}
            d = d[key]
        d[keys[-1]] = value

    def getpath(self, path, default=None):
        return stats_getpath(self, path, default)

    def delpath(self, path):
        d = self
        keys = path.split('/')
        for key in keys[:-1]:
            if key in d:
                d = d[key]
            else:
                return
        del d[keys[-1]]

    def incpath(self, path, value_diff=1):
        curvalue = self.getpath(path) or 0
        self.setpath(path, curvalue + value_diff)

    def _domain_open(self, domain, spider):
        dispatcher.send(signal=self.domain_open, sender=self.__class__, domain=domain, spider=spider)

    def _domain_closed(self, domain, spider, status):
        dispatcher.send(signal=self.domain_closing, sender=self.__class__, domain=domain, spider=spider, status=status)
        if self.debug:
            log.msg(pprint.pformat(self[domain]), domain=domain, level=log.DEBUG)
        if self.db:
            self.db.put(domain, self[domain])
        if self.cleanup:
            del self[domain]
        dispatcher.send(signal=self.domain_closed, sender=self.__class__, domain=domain, spider=spider, status=status)
