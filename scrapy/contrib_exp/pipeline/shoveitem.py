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

        dispatcher.connect(self.spider_opened, signal=signals.spider_opened)
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)

    def process_item(self, spider, item):
        guid = str(item.guid)

        if guid in self.stores[spider]:
            if self.stores[spider][guid] == item:
                status = 'old'
            else:
                status = 'upd'
        else:
            status = 'new'

        if not status == 'old':
            self.stores[spider][guid] = item
        self.log(spider, item, status)
        return item

    def spider_opened(self, spider):
        uri = Template(self.uritpl).substitute(domain=spider.domain_name)
        self.stores[spider] = Shove(uri, **self.opts)

    def spider_closed(self, spider):
        self.stores[spider].sync()

    def log(self, spider, item, status):
        log.msg("Shove (%s): Item guid=%s" % (status, item.guid), level=log.DEBUG, \
            spider=spider)
