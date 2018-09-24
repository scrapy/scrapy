# -*- coding: utf-8 -*-
from __future__ import absolute_import
from collections import defaultdict
import traceback
import warnings

from zope.interface import implementer

from scrapy.interfaces import ISpiderLoader
from scrapy.utils.misc import walk_modules, walk_modules_with_message
from scrapy.utils.spider import iter_spider_classes


@implementer(ISpiderLoader)
class SpiderLoader(object):
    """
    SpiderLoader is a class which locates and loads spiders
    in a Scrapy project.
    """
    def __init__(self, settings):
        self.spider_modules = settings.getlist('SPIDER_MODULES')
        self.warn_only = settings.getbool('SPIDER_LOADER_WARN_ONLY')
        self._spiders = {}
        # eigen modified
        self.failed_modules = {}
        # end
        # ------------
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

    # def _load_all_spiders(self):
    #     for name in self.spider_modules:
    #         try:
    #             for module in walk_modules(name):
    #                 self._load_spiders(module)
    #         except ImportError as e:
    #             if self.warn_only:
    #                 msg = ("\n{tb}Could not load spiders from module '{modname}'. "
    #                        "See above traceback for details.".format(
    #                             modname=name, tb=traceback.format_exc()))
    #                 warnings.warn(msg, RuntimeWarning)
    #             else:
    #                 raise
    #     self._check_name_duplicates()
    # eigen modified
    # 加载爬虫时不会crash
    def _load_all_spiders(self):
        for name in self.spider_modules:
            try:
                modules, failed_modules = walk_modules_with_message(name)
                self.failed_modules.update(failed_modules)
                for module in modules:
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
        """
        Return the Spider class for the given spider name. If the spider
        name is not found, raise a KeyError.
        """
        try:
            return self._spiders[spider_name]
        except KeyError:
            # eigen modified
            # 爬虫启动时候提示报错信息
            # issue: https://github.com/EigenLab/Dcrawl_engine/issues/188
            if self.failed_modules:
                for module in self.failed_modules:
                    msg = self.failed_modules[module].message
                    warnings.warn(msg, RuntimeWarning)
                    print (msg)
            # end
            # ------------------------------------------
            raise KeyError("Spider not found: {}".format(spider_name))

    def find_by_request(self, request):
        """
        Return the list of spider names that can handle the given request.
        """
        return [name for name, cls in self._spiders.items()
                if cls.handles_request(request)]

    def list(self):
        """
        Return a list with the names of all spiders available in the project.
        """
        return list(self._spiders.keys())
