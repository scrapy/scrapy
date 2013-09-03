"""
SpiderManager is the class which locates and manages all website-specific
spiders
"""

from zope.interface import implements

from scrapy import signals
from scrapy.interfaces import ISpiderManager
from scrapy.utils.misc import walk_modules
from scrapy.utils.spider import iter_spider_classes


class SpiderManager(object):

    implements(ISpiderManager)

    def __init__(self, spider_modules):
        self.spider_modules = spider_modules
        self._spiders = {}
        for name in self.spider_modules:
            for module in walk_modules(name):
                self._load_spiders(module)

    def _load_spiders(self, module):
        for spcls in iter_spider_classes(module):
            self._spiders[spcls.name] = spcls

    @classmethod
    def from_settings(cls, settings):
        return cls(settings.getlist('SPIDER_MODULES'))

    @classmethod
    def from_crawler(cls, crawler):
        sm = cls.from_settings(crawler.settings)
        sm.crawler = crawler
        crawler.signals.connect(sm.close_spider, signals.spider_closed)
        return sm

    def create(self, spider_name, **spider_kwargs):
        try:
            spcls = self._spiders[spider_name]
        except KeyError:
            raise KeyError("Spider not found: %s" % spider_name)
        if hasattr(self, 'crawler') and hasattr(spcls, 'from_crawler'):
            return spcls.from_crawler(self.crawler, **spider_kwargs)
        else:
            return spcls(**spider_kwargs)

    def find_by_request(self, request):
        return [name for name, cls in self._spiders.iteritems()
            if cls.handles_request(request)]

    def list(self):
        return self._spiders.keys()

    def close_spider(self, spider, reason):
        closed = getattr(spider, 'closed', None)
        if callable(closed):
            return closed(reason)
