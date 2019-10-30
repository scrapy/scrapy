import logging

from twisted.internet import task

from scrapy.exceptions import NotConfigured
from scrapy import signals

logger = logging.getLogger(__name__)


class LogStats:
    """Log basic scraping stats periodically like:
        * RPM - Requests per Minute
        * IPM - Items per Minute
    """

    def __init__(self, stats, interval=60.0):
        self.stats = stats
        self.interval = interval
        self.multiplier = 60.0 / self.interval
        self.task = None

    @classmethod
    def from_crawler(cls, crawler):
        interval = crawler.settings.getfloat('LOGSTATS_INTERVAL')
        if not interval:
            raise NotConfigured
        o = cls(crawler.stats, interval)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_opened(self, spider):
        self.pagesprev = 0
        self.itemsprev = 0

        self.task = task.LoopingCall(self.log, spider)
        self.task.start(self.interval)

    def log(self, spider):
        self.calculate_stats()

        msg = ("Crawled %(pages)d pages (at %(pagerate)d pages/min), "
               "scraped %(items)d items (at %(itemrate)d items/min)")
        log_args = {'pages': self.pages, 'pagerate': self.prate,
                    'items': self.items, 'itemrate': self.irate}
        logger.info(msg, log_args, extra={'spider': spider})

    def spider_closed(self, spider, reason):
        if self.task and self.task.running:
            self.task.stop()

        self.calculate_stats()
        self.stats.set_value('IPM', self.irate)
        self.stats.set_value('RPM', self.prate)

    def calculate_stats(self):
        self.items = self.stats.get_value('item_scraped_count', 0)
        self.pages = self.stats.get_value('response_received_count', 0)
        self.irate = (self.items - self.itemsprev) * self.multiplier
        self.prate = (self.pages - self.pagesprev) * self.multiplier
        self.pagesprev, self.itemsprev = self.pages, self.items
