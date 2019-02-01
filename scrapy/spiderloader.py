# -*- coding: utf-8 -*-
from __future__ import absolute_import
from collections import defaultdict
import traceback
import warnings

from zope.interface import implementer

from scrapy.interfaces import ISpiderLoader
from scrapy.utils.misc import walk_modules
from scrapy.utils.spider import iter_spider_classes


@implementer(ISpiderLoader)
class SpiderLoader(object):
    """Default implementation of the
    :interface:`ISpiderLoader <scrapy.interfaces.ISpiderLoader>` interface.

    It loads the :class:`Spider <scrapy.Spider>` subclasses found recursively
    in the modules of the :setting:`SPIDER_MODULES` setting.

    It resolves :class:`Spider <scrapy.Spider>` subclasses based on their
    :class:`name <scrapy.Spider.name>`.

    It matches a :class:`Spider <scrapy.Spider>` subclass to a
    :class:`Request <scrapy.Request>` object when the domain name of
    the request URL is a perfect match or a subdomain of the :class:`name
    <scrapy.Spider.name>` or any of the :class:`allowed_domains
    <scrapy.Spider.allowed_domains>` of that :class:`Spider <scrapy.Spider>`
    subclass.
    """

    def __init__(self, settings):
        self.spider_modules = settings.getlist('SPIDER_MODULES')
        self.warn_only = settings.getbool('SPIDER_LOADER_WARN_ONLY')
        self._spiders = {}
        self._found = defaultdict(list)
        self._load_all_spiders()

    def _check_name_duplicates(self):
        dupes = ["\n".join("  {cls} named {name!r} (in {module})".format(
                                module=mod, cls=cls, name=name)
                           for (mod, cls) in locations)
                 for name, locations in self._found.items()
                 if len(locations)>1]
        if dupes:
            msg = ("There are several spiders with the same name:\n\n"
                   "{}\n\n  This can cause unexpected behavior.".format(
                        "\n\n".join(dupes)))
            warnings.warn(msg, UserWarning)

    def _load_spiders(self, module):
        for spcls in iter_spider_classes(module):
            self._found[spcls.name].append((module.__name__, spcls.__name__))
            self._spiders[spcls.name] = spcls

    def _load_all_spiders(self):
        for name in self.spider_modules:
            try:
                for module in walk_modules(name):
                    self._load_spiders(module)
            except ImportError as e:
                if self.warn_only:
                    msg = ("\n{tb}Could not load spiders from module '{modname}'. "
                           "See above traceback for details.".format(
                                modname=name, tb=traceback.format_exc()))
                    warnings.warn(msg, RuntimeWarning)
                else:
                    raise
        self._check_name_duplicates()

    @classmethod
    def from_settings(cls, settings):
        return cls(settings)

    def load(self, spider_name):
        try:
            return self._spiders[spider_name]
        except KeyError:
            raise KeyError("Spider not found: {}".format(spider_name))

    def find_by_request(self, request):
        return [name for name, cls in self._spiders.items()
                if cls.handles_request(request)]

    def list(self):
        return list(self._spiders.keys())
