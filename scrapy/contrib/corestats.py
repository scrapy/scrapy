"""
Extension for collecting core stats like items scraped and start/finish times
"""
import datetime

from scrapy.xlib.pydispatch import dispatcher

from scrapy import signals
from scrapy.stats import stats

class CoreStats(object):

    def __init__(self):
        dispatcher.connect(self.stats_spider_opened, signal=signals.stats_spider_opened)
        dispatcher.connect(self.stats_spider_closing, signal=signals.stats_spider_closing)
        dispatcher.connect(self.item_scraped, signal=signals.item_scraped)
        dispatcher.connect(self.item_dropped, signal=signals.item_dropped)

    def stats_spider_opened(self, spider):
        stats.set_value('start_time', datetime.datetime.utcnow(), spider=spider)

    def stats_spider_closing(self, spider, reason):
        stats.set_value('finish_time', datetime.datetime.utcnow(), spider=spider)
        stats.set_value('finish_reason', reason, spider=spider)

    def item_scraped(self, item, spider):
        stats.inc_value('item_scraped_count', spider=spider)

    def item_dropped(self, item, spider, exception):
        reason = exception.__class__.__name__
        stats.inc_value('item_dropped_count', spider=spider)
        stats.inc_value('item_dropped_reasons_count/%s' % reason, spider=spider)
