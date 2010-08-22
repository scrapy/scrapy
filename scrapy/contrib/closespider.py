"""CloseSpider is an extension that forces spiders to be closed after certain
conditions are met.

See documentation in docs/topics/extensions.rst
"""

from collections import defaultdict

from twisted.internet import reactor
from scrapy.xlib.pydispatch import dispatcher

from scrapy import signals
from scrapy.project import crawler
from scrapy.conf import settings

class CloseSpider(object):

    def __init__(self):
        self.timeout = settings.getint('CLOSESPIDER_TIMEOUT')
        self.itempassed = settings.getint('CLOSESPIDER_ITEMPASSED')

        self.counts = defaultdict(int)
        self.tasks = {}

        if self.timeout:
            dispatcher.connect(self.spider_opened, signal=signals.spider_opened)
        if self.itempassed:
            dispatcher.connect(self.item_passed, signal=signals.item_passed)
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)

    def spider_opened(self, spider):
        self.tasks[spider] = reactor.callLater(self.timeout, \
            crawler.engine.close_spider, spider=spider, \
            reason='closespider_timeout')
        
    def item_passed(self, item, spider):
        self.counts[spider] += 1
        if self.counts[spider] == self.itempassed:
            crawler.engine.close_spider(spider, 'closespider_itempassed')

    def spider_closed(self, spider):
        self.counts.pop(spider, None)
        tsk = self.tasks.pop(spider, None)
        if tsk and tsk.active():
            tsk.cancel()
