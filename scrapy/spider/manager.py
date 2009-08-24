"""
SpiderManager is the class which locates and manages all website-specific
spiders
"""
import sys
import urlparse

from twisted.plugin import getCache

from scrapy.spider.models import ISpider
from scrapy import log
from scrapy.conf import settings
from scrapy.utils.url import url_is_from_spider
from scrapy.utils.misc import load_object

class SpiderManager(object):
    """Spider locator and manager"""

    def __init__(self):
        self.loaded = False
        self.default_domain = None
        self.force_domain = None
        self.spider_modules = None

    def fromdomain(self, domain_name):
        return self.asdict().get(domain_name)

    def fromurl(self, url):
        self._load_on_demand()
        if self.force_domain:
            return self.asdict().get(self.force_domain)
        domain = urlparse.urlparse(url).hostname
        domain = str(domain).replace('www.', '')
        if domain:
            if domain in self.asdict():         # try first locating by domain
                return self.asdict()[domain]
            else:                               # else search spider by spider
                plist = self.asdict().values()
                for p in plist:
                    if url_is_from_spider(url, p):
                        return p
        spider = self.asdict().get(self.default_domain)
        if not spider:                          # create a custom spider
            spiderclassname = settings.get('DEFAULT_SPIDER')
            if spiderclassname:
                spider = load_object(spiderclassname)(domain)
                self.add_spider(spider)
            
        return spider

    def asdict(self):
        self._load_on_demand()
        return self._spiders

    def _load_on_demand(self):
        if not self.loaded:
            self.load()

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
        try:
            ISpider.validateInvariants(spider)
            self._spiders[spider.domain_name] = spider
        except Exception, e:
            self._invaliddict[spider.domain_name] = spider
            # we can't use the log module here because it may not be available yet
            print "WARNING: Could not load spider %s: %s" % (spider, e)

    def reload(self, spider_modules=None, skip_domains=None):
        """Reload spiders by trying to discover any spiders added under the
        spiders module/packages, removes any spiders removed.

        If skip_domains is passed those spiders won't be reloaded.
        """
        skip_domains = set(skip_domains or [])
        modules = [__import__(m, {}, {}, ['']) for m in self.spider_modules]
        for m in modules:
            reload(m)
        reloaded = 0
        pdict = self.asdict()
        for domain, spider in pdict.iteritems():
            if not domain in skip_domains:
                reload(sys.modules[spider.__module__])
                reloaded += 1
        self.load(spider_modules=spider_modules)  # second call to update spider instances
        log.msg("Reloaded %d/%d scrapy spiders" % (reloaded, len(pdict)), level=log.DEBUG)

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
