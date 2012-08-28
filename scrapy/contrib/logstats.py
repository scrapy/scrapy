from twisted.internet import task

from scrapy.exceptions import NotConfigured
from scrapy import log, signals

class Slot(object):

    def __init__(self):
        self.items = 0
        self.itemsprev = 0
        self.pages = 0
        self.pagesprev = 0

class LogStats(object):
    """Log basic scraping stats periodically"""

    def __init__(self, interval=60.0):
        self.interval = interval
        self.slots = {}
        self.multiplier = 60.0 / self.interval

    @classmethod
    def from_crawler(cls, crawler):
        interval = settings.getfloat('LOGSTATS_INTERVAL')
        if not interval:
            raise NotConfigured
        o = cls(interval)
        crawler.signals.connect(o.item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(o.response_received, signal=signals.response_received)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(o.engine_started, signal=signals.engine_started)
        crawler.signals.connect(o.engine_stopped, signal=signals.engine_stopped)
        return o

    @classmethod
    def from_crawler(cls, crawler):
        interval = crawler.settings.getfloat('LOGSTATS_INTERVAL')
        if not interval:
            raise NotConfigured
        return cls(interval)

    def item_scraped(self, spider):
        self.slots[spider].items += 1

    def response_received(self, spider):
        self.slots[spider].pages += 1

    def spider_opened(self, spider):
        self.slots[spider] = Slot()

    def spider_closed(self, spider):
        del self.slots[spider]

    def engine_started(self):
        self.tsk = task.LoopingCall(self.log)
        self.tsk.start(self.interval)

    def log(self):
        for spider, slot in self.slots.items():
            irate = (slot.items - slot.itemsprev) * self.multiplier
            prate = (slot.pages - slot.pagesprev) * self.multiplier
            slot.pagesprev, slot.itemsprev = slot.pages, slot.items
            msg = "Crawled %d pages (at %d pages/min), scraped %d items (at %d items/min)" \
                % (slot.pages, prate, slot.items, irate)
            log.msg(msg, spider=spider)

    def engine_stopped(self):
        if self.tsk.running:
            self.tsk.stop()
