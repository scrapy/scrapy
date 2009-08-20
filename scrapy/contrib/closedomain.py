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
            dispatcher.connect(self.domain_opened, signal=signals.domain_opened)
        if self.itempassed:
            dispatcher.connect(self.item_passed, signal=signals.item_passed)
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

    def domain_opened(self, domain):
        self.tasks[domain] = reactor.callLater(self.timeout, scrapyengine.close_domain, \
            domain=domain, reason='closedomain_timeout')
        
    def item_passed(self, item, spider):
        self.counts[spider.domain_name] += 1
        if self.counts[spider.domain_name] == self.itempassed:
            scrapyengine.close_domain(spider.domain_name, 'closedomain_itempassed')

    def domain_closed(self, domain):
        self.counts.pop(domain, None)
        tsk = self.tasks.pop(domain, None)
        if tsk and not tsk.called:
            tsk.cancel()
