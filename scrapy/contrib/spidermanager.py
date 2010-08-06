"""
SpiderManager is the class which locates and manages all website-specific
spiders
"""

import inspect

from scrapy import log
from scrapy.conf import settings
from scrapy.utils.misc import walk_modules
from scrapy.spider import BaseSpider


class SpiderManager(object):

    def __init__(self):
        self.loaded = False
        self._spiders = {}

    def create(self, spider_name, **spider_kwargs):
        """Returns a Spider instance for the given spider name, using the given
        spider arguments. If the sipder name is not found, it raises a
        KeyError.
        """
        return self._spiders[spider_name](**spider_kwargs)

    def find_by_request(self, request):
        """Returns list of spiders names that match the given Request"""
        return [name for name, spider in self._spiders.iteritems()
                if spider.handles_request(request)]

    def create_for_request(self, request, default_spider=None, \
            log_none=False, log_multiple=False, **spider_kwargs):
        """Create a spider to handle the given Request.

        This will look for the spiders that can handle the given request (using
        find_by_request) and return a (new) Spider if (and only if) there is
        only one Spider able to handle the Request.

        If multiple spiders (or no spider) are found, it will return the
        default_spider passed. It can optionally log if multiple or no spiders
        are found.
        """
        snames = self.find_by_request(request)
        if len(snames) == 1:
            return self.create(snames[0], **spider_kwargs)
        if len(snames) > 1 and log_multiple:
            log.msg('More than one spider can handle: %s - %s' % \
                (request, ", ".join(snames)), log.ERROR)
        if len(snames) == 0 and log_none:
            log.msg('Unable to find spider that handles: %s' % request, log.ERROR)
        return default_spider

    def list(self):
        """Returns list of spiders available."""
        return self._spiders.keys()

    def load(self, spider_modules=None):
        """Load spiders from spider_modules or SPIDER_MODULES setting."""
        if spider_modules is None:
            spider_modules = settings.getlist('SPIDER_MODULES')
        self.spider_modules = spider_modules

        self._spiders = {}
        for name in self.spider_modules:
            for module in walk_modules(name):
                self._load_spiders(module)
        self.loaded = True

    def _load_spiders(self, module):
        for obj in vars(module).itervalues():
            if inspect.isclass(obj) and issubclass(obj, BaseSpider):
                name = getattr(obj, 'name', None)
                if name is not None:
                    self._spiders[name] = obj

    def close_spider(self, spider):
        pass
