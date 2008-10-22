"""
A pipeline to persist objects using shove. 

New is a "new generation" shelve. For more information see: 
http://pypi.python.org/pypi/shove
"""

from string import Template

from shove import Shove
from pydispatch import dispatcher

from scrapy.core import signals
from scrapy.conf import settings

class ShoveItemPipeline(object):

    def __init__(self):
        self.uritpl = settings['SHOVEITEM_STORE_URI']
        if not self.uritpl:
            raise NotConfigured
        self.opts = settings['SHOVEITEM_STORE_OPT'] or {}
        self.stores = {}

        dispatcher.connect(self.domain_open, signal=signals.domain_open)
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

    def process_item(self, domain, response, item):
        self.stores[domain][str(item.guid)] = item
        return item

    def domain_open(self, domain):
        uri = Template(self.uritpl).substitute(domain=domain)
        self.stores[domain] = Shove(uri, **self.opts)

    def domain_closed(self, domain):
        self.stores[domain].sync()
