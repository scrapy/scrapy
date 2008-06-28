"""
Reload spider modules once they are finished scraping

This is to release any resources held on to by scraping spiders.
"""
import sys
from pydispatch import dispatcher
from scrapy.core import log, signals

class SpiderReloader(object):

    def __init__(self):
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

    def domain_closed(self, domain, spider):
        module = spider.__module__
        log.msg("reloading module %s" % module, domain=domain)
        reload(sys.modules[module])
