"""
DelayedCloseDomain is an extension that keeps open a domain until a
configurable amount of idle time is reached
"""

from datetime import datetime

from pydispatch import dispatcher
from collections import defaultdict

from scrapy.core import signals
from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import NotConfigured, DontCloseDomain
from scrapy.conf import settings


class DelayedCloseDomain(object):
    def __init__(self):
        self.delay = settings.getint('DOMAIN_CLOSE_DELAY')
        if not self.delay:
            raise NotConfigured

        self.opened_at = defaultdict(datetime.now)
        dispatcher.connect(self.domain_idle, signal=signals.domain_idle)
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

    def domain_idle(self, domain):
        try:
            lastseen = scrapyengine.downloader.sites[domain].lastseen
        except KeyError:
            lastseen = None
        if not lastseen:
            lastseen = self.opened_at[domain]

        delta = datetime.now() - lastseen
        if delta.seconds < self.delay:
            raise DontCloseDomain

    def domain_closed(self, domain):
        self.opened_at.pop(domain, None)
