"""
SpiderManager is the class which locates and manages all website-specific
spiders
"""
import sys
import os
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
        self.spider_modules = settings.getlist('SPIDER_MODULES')
        self.force_domain = None

    @property
    def all(self):
        self._load_on_demand()
        return self._alldict.values()

    @property
    def enabled(self):
        self._load_on_demand()
        return self._enableddict.values()

    def fromdomain(self, domain_name, include_disabled=True): 
        return self.asdict(include_disabled=include_disabled).get(domain_name)

    def fromurl(self, url, include_disabled=True):
        self._load_on_demand()
        if self.force_domain:
            return self._alldict.get(self.force_domain)
        domain = urlparse.urlparse(url).hostname
        domain = str(domain).replace('www.', '')
        if domain:
            if domain in self._alldict:         # try first locating by domain
                return self._alldict[domain]
            else:                               # else search spider by spider
                plist = self.all if include_disabled else self.enabled
                for p in plist:
                    if url_is_from_spider(url, p):
                        return p
        spider = self._alldict.get(self.default_domain)
        if not spider:                          # create a custom spider
            spiderclassname = settings.get('DEFAULT_SPIDER')
            if spiderclassname:
                spider = load_object(spiderclassname)(domain)
                self.add_spider(spider)
            
        return spider

    def asdict(self, include_disabled=True):
        self._load_on_demand()
        return self._alldict if include_disabled else self._enableddict

    def _load_on_demand(self):
        if not self.loaded:
            self.load()

    def _enabled_spiders(self):
        if settings['ENABLED_SPIDERS']:
            return set(settings['ENABLED_SPIDERS'])
        elif settings['ENABLED_SPIDERS_FILE']:
            if os.path.exists(settings['ENABLED_SPIDERS_FILE']):
                lines = open(settings['ENABLED_SPIDERS_FILE']).readlines()
                return set([l.strip() for l in lines if not l.strip().startswith('#')])
            else:
                return set()
        else:
            return set()

    def load(self):
        self._invaliddict = {}
        self._alldict = {}
        self._enableddict = {}
        self._enabled_spiders_set = self._enabled_spiders()

        modules = [__import__(m, {}, {}, ['']) for m in self.spider_modules]
        for module in modules:
            for spider in self._getspiders(ISpider, module):
                self.add_spider(spider)
        self.loaded = True

    def add_spider(self, spider):
        try:
            ISpider.validateInvariants(spider)
            self._alldict[spider.domain_name] = spider
            if spider.domain_name in self._enabled_spiders_set:
                self._enableddict[spider.domain_name] = spider
        except Exception, e:
            self._invaliddict[spider.domain_name] = spider
            # we can't use the log module here because it may not be available yet
            print "WARNING: Could not load spider %s: %s" % (spider, e)

    def reload(self, skip_domains=None):
        """
        Reload all enabled spiders.

        This discovers any spiders added under the spiders module/packages,
        removes any spiders removed, updates all enabled spiders code and
        updates list of enabled spiders from ENABLED_SPIDERS_FILE or
        ENABLED_SPIDERS setting.

        Disabled spiders are intentionally excluded to avoid
        syntax/initialization errors. Currently running spiders are also
        excluded to avoid inconsistent behaviours.

        If skip_domains is passed those spiders won't be reloaded.

        """
        skip_domains = set(skip_domains or [])
        modules = [__import__(m, {}, {}, ['']) for m in self.spider_modules]
        for m in modules:
            reload(m)
        self.load()  # first call to update list of enabled spiders
        reloaded = 0
        pdict = self.asdict(include_disabled=False)
        for domain, spider in pdict.iteritems():
            if not domain in skip_domains:
                reload(sys.modules[spider.__module__])
                reloaded += 1
        self.load()  # second call to update spider instances
        log.msg("Reloaded %d/%d scrapy spiders" % (reloaded, len(pdict)), level=log.DEBUG)

    def _getspiders(self, interface, package):
        """
        This is an override of twisted.plugin.getPlugin, because we're
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
