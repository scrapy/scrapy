from collections import defaultdict

from twisted.internet import task

from scrapy.xlib.pydispatch import dispatcher
from scrapy.exceptions import NotConfigured
from scrapy.conf import settings
from scrapy import log, signals

class Slot(object):

    def __init__(self):
        self.items = 0
        self.itemsprev = 0
        self.pages = 0
        self.pagesprev = 0

class LogStats(object):
    """Log basic scraping stats periodically"""

    def __init__(self):
        self.interval = settings.getfloat('LOGSTATS_INTERVAL')
        if not self.interval:
            raise NotConfigured
        self.slots = defaultdict(Slot)
        self.multiplier = 60.0 / self.interval
        dispatcher.connect(self.item_scraped, signal=signals.item_scraped)
        dispatcher.connect(self.response_received, signal=signals.response_received)
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)
        dispatcher.connect(self.engine_started, signal=signals.engine_started)
        dispatcher.connect(self.engine_stopped, signal=signals.engine_stopped)

    def item_scraped(self, spider):
        self.slots[spider].items += 1

    def response_received(self, spider):
        self.slots[spider].pages += 1

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
