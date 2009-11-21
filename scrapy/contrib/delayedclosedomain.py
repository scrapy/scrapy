"""
DelayedCloseDomain is an extension that keeps open a domain until a
configurable amount of idle time is reached
"""

from time import time

from scrapy.xlib.pydispatch import dispatcher
from collections import defaultdict

from scrapy.core import signals
from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import NotConfigured, DontCloseSpider
from scrapy.conf import settings


class DelayedCloseDomain(object):
    def __init__(self):
        self.delay = settings.getint('DOMAIN_CLOSE_DELAY')
        if not self.delay:
            raise NotConfigured

        self.opened_at = defaultdict(time)
        dispatcher.connect(self.spider_idle, signal=signals.spider_idle)
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)

    def spider_idle(self, spider):
        try:
            lastseen = scrapyengine.downloader.sites[spider].lastseen
        except KeyError:
            lastseen = None
        if not lastseen:
            lastseen = self.opened_at[spider]

        if time() < lastseen + self.delay:
            raise DontCloseSpider

    def spider_closed(self, spider):
        self.opened_at.pop(spider, None)
