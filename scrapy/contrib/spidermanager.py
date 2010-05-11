"""
SpiderManager is the class which locates and manages all website-specific
spiders
"""

import sys

from twisted.plugin import getCache
from twisted.python.rebuild import rebuild

from scrapy.spider.models import ISpider
from scrapy import log
from scrapy.conf import settings
from scrapy.utils.url import url_is_from_spider

class TwistedPluginSpiderManager(object):
    """Spider manager based in Twisted Plugin System"""

    def __init__(self):
        self.loaded = False
        self._spiders = {}

    def create(self, spider_name, **spider_kwargs):
        """Returns a Spider instance for the given spider name, using the given
        spider arguments. If the sipder name is not found, it raises a
        KeyError.
        """
        spider = self._spiders[spider_name]
        spider.__dict__.update(spider_kwargs)
        return spider

    def find_by_request(self, request):
        """Returns list of spiders names that match the given Request"""
        return [name for name, spider in self._spiders.iteritems()
                if url_is_from_spider(request.url, spider)]

    def list(self):
        """Returns list of spiders available."""
        return self._spiders.keys()

    def load(self, spider_modules=None):
        """Load spiders from module directory."""
        if spider_modules is None:
            spider_modules = settings.getlist('SPIDER_MODULES')
        self.spider_modules = spider_modules
        self._spiders = {}

        modules = [__import__(m, {}, {}, ['']) for m in self.spider_modules]
        for module in modules:
            for spider in self._getspiders(ISpider, module):
                ISpider.validateInvariants(spider)
                self._spiders[spider.name] = spider
        self.loaded = True

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

    def close_spider(self, spider):
        """Reload spider module to release any resources held on to by the
        spider
        """
        name = spider.name
        if name not in self._spiders:
            return
        spider = self._spiders[name]
        module_name = spider.__module__
        module = sys.modules[module_name]
        if hasattr(module, 'SPIDER'):
            log.msg("Reloading module %s" % module_name, spider=spider, \
                level=log.DEBUG)
            new_module = rebuild(module, doLog=0)
            self._spiders[name] = new_module.SPIDER
