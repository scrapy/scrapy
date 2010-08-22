"""
Scrapy extension for collecting scraping stats
"""
import os
import getpass
import socket
import datetime

from scrapy.xlib.pydispatch import dispatcher

from scrapy import signals
from scrapy.stats import stats
from scrapy.conf import settings

class CoreStats(object):
    """Scrapy core stats collector"""

    def __init__(self):
        stats.set_value('envinfo/user', getpass.getuser())
        stats.set_value('envinfo/host', socket.gethostname())
        stats.set_value('envinfo/logfile', settings['LOG_FILE'])
        stats.set_value('envinfo/pid', os.getpid())

        dispatcher.connect(self.stats_spider_opened, signal=signals.stats_spider_opened)
        dispatcher.connect(self.stats_spider_closing, signal=signals.stats_spider_closing)
        dispatcher.connect(self.item_scraped, signal=signals.item_scraped)
        dispatcher.connect(self.item_passed, signal=signals.item_passed)
        dispatcher.connect(self.item_dropped, signal=signals.item_dropped)

    def stats_spider_opened(self, spider):
        stats.set_value('start_time', datetime.datetime.utcnow(), spider=spider)
        stats.set_value('envinfo/host', stats.get_value('envinfo/host'), spider=spider)
        stats.inc_value('spider_count/opened')

    def stats_spider_closing(self, spider, reason):
        stats.set_value('finish_time', datetime.datetime.utcnow(), spider=spider)
        stats.set_value('finish_status', 'OK' if reason == 'finished' else reason, spider=spider)
        stats.inc_value('spider_count/%s' % reason, spider=spider)

    def item_scraped(self, item, spider):
        stats.inc_value('item_scraped_count', spider=spider)
        stats.inc_value('item_scraped_count')

    def item_passed(self, item, spider):
        stats.inc_value('item_passed_count', spider=spider)
        stats.inc_value('item_passed_count')

    def item_dropped(self, item, spider, exception):
        reason = exception.__class__.__name__
        stats.inc_value('item_dropped_count', spider=spider)
        stats.inc_value('item_dropped_reasons_count/%s' % reason, spider=spider)
        stats.inc_value('item_dropped_count')
