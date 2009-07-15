"""
Scrapy extension for collecting scraping stats
"""
import os
import getpass
import socket
import datetime

from scrapy.xlib.pydispatch import dispatcher

from scrapy.core import signals
from scrapy.stats import stats
from scrapy.stats.signals import stats_domain_opened, stats_domain_closing
from scrapy.conf import settings

class CoreStats(object):
    """Scrapy core stats collector"""

    def __init__(self):
        stats.set_value('envinfo/user', getpass.getuser())
        stats.set_value('envinfo/host', socket.gethostname())
        stats.set_value('envinfo/logfile', settings['LOGFILE'])
        stats.set_value('envinfo/pid', os.getpid())

        dispatcher.connect(self.stats_domain_opened, signal=stats_domain_opened)
        dispatcher.connect(self.stats_domain_closing, signal=stats_domain_closing)
        dispatcher.connect(self.item_scraped, signal=signals.item_scraped)
        dispatcher.connect(self.item_passed, signal=signals.item_passed)
        dispatcher.connect(self.item_dropped, signal=signals.item_dropped)

    def stats_domain_opened(self, domain):
        stats.set_value('start_time', datetime.datetime.now(), domain=domain)
        stats.set_value('envinfo/host', stats.get_value('envinfo/host'), domain=domain)
        stats.inc_value('domain_count/opened')

    def stats_domain_closing(self, domain, reason):
        stats.set_value('finish_time', datetime.datetime.now(), domain=domain)
        stats.set_value('finish_status', 'OK' if reason == 'finished' else reason, domain=domain)
        stats.inc_value('domain_count/%s' % reason, domain=domain)

    def item_scraped(self, item, spider):
        stats.inc_value('item_scraped_count', domain=spider.domain_name)
        stats.inc_value('item_scraped_count')

    def item_passed(self, item, spider):
        stats.inc_value('item_passed_count', domain=spider.domain_name)
        stats.inc_value('item_passed_count')

    def item_dropped(self, item, spider, exception):
        reason = exception.__class__.__name__
        stats.inc_value('item_dropped_count', domain=spider.domain_name)
        stats.inc_value('item_dropped_reasons_count/%s' % reason, domain=spider.domain_name)
        stats.inc_value('item_dropped_count')
