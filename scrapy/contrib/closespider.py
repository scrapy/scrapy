"""CloseSpider is an extension that forces spiders to be closed after certain
conditions are met.

See documentation in docs/topics/extensions.rst
"""

from collections import defaultdict

from twisted.internet import reactor
from twisted.python import log as txlog

from scrapy import signals, log

class CloseSpider(object):

    def __init__(self, crawler):
        self.crawler = crawler
        self.timeout = crawler.settings.getint('CLOSESPIDER_TIMEOUT')
        self.itemcount = crawler.settings.getint('CLOSESPIDER_ITEMCOUNT')
        self.pagecount = crawler.settings.getint('CLOSESPIDER_PAGECOUNT')
        self.errorcount = crawler.settings.getint('CLOSESPIDER_ERRORCOUNT')

        self.errorcounts = defaultdict(int)
        self.pagecounts = defaultdict(int)
        self.counts = defaultdict(int)
        self.tasks = {}

        if self.errorcount:
            txlog.addObserver(self.catch_log)
        if self.pagecount:
            crawler.signals.connect(self.page_count, signal=signals.response_received)
        if self.timeout:
            crawler.signals.connect(self.spider_opened, signal=signals.spider_opened)
        if self.itemcount:
            crawler.signals.connect(self.item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(self.spider_closed, signal=signals.spider_closed)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def catch_log(self, event):
        if event.get('logLevel') == log.ERROR:
            spider = event.get('spider')
            if spider:
                self.errorcounts[spider] += 1
                if self.errorcounts[spider] == self.errorcount:
                    self.crawler.engine.close_spider(spider, 'closespider_errorcount')

    def page_count(self, response, request, spider):
        self.pagecounts[spider] += 1
        if self.pagecounts[spider] == self.pagecount:
            self.crawler.engine.close_spider(spider, 'closespider_pagecount')

    def spider_opened(self, spider):
        self.tasks[spider] = reactor.callLater(self.timeout, \
            self.crawler.engine.close_spider, spider=spider, \
            reason='closespider_timeout')

    def item_scraped(self, item, spider):
        self.counts[spider] += 1
        if self.counts[spider] == self.itemcount:
            self.crawler.engine.close_spider(spider, 'closespider_itemcount')

    def spider_closed(self, spider):
        self.counts.pop(spider, None)
        self.pagecounts.pop(spider, None)
        self.errorcounts.pop(spider, None)
        tsk = self.tasks.pop(spider, None)
        if tsk and tsk.active():
            tsk.cancel()
