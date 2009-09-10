"""
SpiderManager is the class which locates and manages all website-specific
spiders
"""

import sys
import urlparse

from twisted.plugin import getCache
from twisted.python.rebuild import rebuild

from scrapy.spider.models import ISpider
from scrapy import log
from scrapy.conf import settings
from scrapy.utils.url import url_is_from_spider

class TwistedPluginSpiderManager(object):
    """Spider locator and manager"""

    def __init__(self):
        self.loaded = False
        self.force_domain = None
        self._invaliddict = {}
        self._spiders = {}

    def fromdomain(self, domain):
        return self._spiders.get(domain)

    def fromurl(self, url):
        if self.force_domain:
            return self._spiders.get(self.force_domain)
        domain = urlparse.urlparse(url).hostname
        domain = str(domain).replace('www.', '')
        if domain:
            if domain in self._spiders:         # try first locating by domain
                return self._spiders[domain]
            else:                               # else search spider by spider
                plist = self._spiders.values()
                for p in plist:
                    if url_is_from_spider(url, p):
                        return p

    def list(self):
        return self._spiders.keys()

    def load(self, spider_modules=None):
        if spider_modules is None:
            spider_modules = settings.getlist('SPIDER_MODULES')
        self.spider_modules = spider_modules
        self._invaliddict = {}
        self._spiders = {}

        modules = [__import__(m, {}, {}, ['']) for m in self.spider_modules]
        for module in modules:
            for spider in self._getspiders(ISpider, module):
                self.add_spider(spider)
        self.loaded = True

    def add_spider(self, spider):
        ISpider.validateInvariants(spider)
        self._spiders[spider.domain_name] = spider

    def _getspiders(self, interface, package):
        """This is an override of twisted.plugin.getPlugin, because we're
        interested in catching exceptions thrown when loading spiders such as
        KeyboardInterrupt
        """
        try:
            allDropins = getCache(package)
            for dropin in allDropins.itervalues():
                for plugin in dropin.plugins:
                    adapted = interface(plugin, None)
                    if adapted is not None:
                        yield adapted
        except KeyboardInterrupt:
            sys.stderr.write("Interrupted while loading Scrapy spiders\n")
            sys.exit(2)

    def close_domain(self, domain):
        """Reload spider module to release any resources held on to by the
        spider
        """
        spider = self._spiders[domain]
        module_name = spider.__module__
        module = sys.modules[module_name]
        if hasattr(module, 'SPIDER'):
            log.msg("Reloading module %s" % module_name, domain=domain, \
                level=log.DEBUG)
            new_module = rebuild(module, doLog=0)
            self._spiders[domain] = new_module.SPIDER
