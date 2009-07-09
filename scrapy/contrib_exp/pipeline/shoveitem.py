"""
A pipeline to persist objects using shove. 

Shove is a "new generation" shelve. For more information see: 
http://pypi.python.org/pypi/shove
"""

from string import Template

from shove import Shove
from scrapy.xlib.pydispatch import dispatcher

from scrapy import log
from scrapy.core import signals
from scrapy.conf import settings
from scrapy.core.exceptions import NotConfigured

class ShoveItemPipeline(object):

    def __init__(self):
        self.uritpl = settings['SHOVEITEM_STORE_URI']
        if not self.uritpl:
            raise NotConfigured
        self.opts = settings['SHOVEITEM_STORE_OPT'] or {}
        self.stores = {}

        dispatcher.connect(self.domain_open, signal=signals.domain_open)
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

    def process_item(self, domain, item):
        guid = str(item.guid)

        if guid in self.stores[domain]:
            if self.stores[domain][guid] == item:
                status = 'old'
            else:
                status = 'upd'
        else:
            status = 'new'

        if not status == 'old':
            self.stores[domain][guid] = item
        self.log(domain, item, status)
        return item

    def domain_open(self, domain):
        uri = Template(self.uritpl).substitute(domain=domain)
        self.stores[domain] = Shove(uri, **self.opts)

    def domain_closed(self, domain):
        self.stores[domain].sync()

    def log(self, domain, item, status):
        log.msg("Shove (%s): Item guid=%s" % (status, item.guid), level=log.DEBUG, domain=domain)
