"""CloseDomain is an extension that forces spiders to be closed after certain
conditions are met.

See documentation in docs/topics/extensions.rst
"""

from collections import defaultdict

from twisted.internet import reactor
from scrapy.xlib.pydispatch import dispatcher

from scrapy.core import signals
from scrapy.core.engine import scrapyengine
from scrapy.conf import settings

class CloseDomain(object):

    def __init__(self):
        self.timeout = settings.getint('CLOSEDOMAIN_TIMEOUT')
        self.itempassed = settings.getint('CLOSEDOMAIN_ITEMPASSED')

        self.counts = defaultdict(int)
        self.tasks = {}

        if self.timeout:
            dispatcher.connect(self.spider_opened, signal=signals.spider_opened)
        if self.itempassed:
            dispatcher.connect(self.item_passed, signal=signals.item_passed)
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)

    def spider_opened(self, spider):
        self.tasks[spider] = reactor.callLater(self.timeout, scrapyengine.close_spider, \
            spider=spider, reason='closedomain_timeout')
        
    def item_passed(self, item, spider):
        self.counts[spider] += 1
        if self.counts[spider] == self.itempassed:
            scrapyengine.close_spider(spider, 'closedomain_itempassed')

    def spider_closed(self, spider):
        self.counts.pop(spider, None)
        tsk = self.tasks.pop(spider, None)
        if tsk and not tsk.called:
            tsk.cancel()
