"""
Extension for collecting core stats like items scraped and start/finish times
"""
import datetime

from scrapy import signals

class CoreStats(object):

    def __init__(self, stats):
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        o = cls(crawler.stats)
        crawler.signals.connect(o.stats_spider_opened, signal=signals.stats_spider_opened)
        crawler.signals.connect(o.stats_spider_closing, signal=signals.stats_spider_closing)
        crawler.signals.connect(o.item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(o.item_dropped, signal=signals.item_dropped)
        return o

    def stats_spider_opened(self, spider):
        self.stats.set_value('start_time', datetime.datetime.utcnow(), spider=spider)

    def stats_spider_closing(self, spider, reason):
        self.stats.set_value('finish_time', datetime.datetime.utcnow(), spider=spider)
        self.stats.set_value('finish_reason', reason, spider=spider)

    def item_scraped(self, item, spider):
        self.stats.inc_value('item_scraped_count', spider=spider)

    def item_dropped(self, item, spider, exception):
        reason = exception.__class__.__name__
        self.stats.inc_value('item_dropped_count', spider=spider)
        self.stats.inc_value('item_dropped_reasons_count/%s' % reason, spider=spider)
