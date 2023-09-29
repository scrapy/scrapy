from __future__ import annotations

import traceback
import warnings
from collections import defaultdict
from types import ModuleType
from typing import TYPE_CHECKING, DefaultDict, Dict, List, Tuple, Type

from zope.interface import implementer

from scrapy import Request, Spider
from scrapy.interfaces import ISpiderLoader
from scrapy.settings import BaseSettings
from scrapy.utils.misc import walk_modules
from scrapy.utils.spider import iter_spider_classes

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self


@implementer(ISpiderLoader)
class SpiderLoader:
    """
    SpiderLoader is a class which locates and loads spiders
    in a Scrapy project.
    """

    def __init__(self, settings: BaseSettings):
        self.spider_modules: List[str] = settings.getlist("SPIDER_MODULES")
        self.warn_only: bool = settings.getbool("SPIDER_LOADER_WARN_ONLY")
        self._spiders: Dict[str, Type[Spider]] = {}
        self._found: DefaultDict[str, List[Tuple[str, str]]] = defaultdict(list)
        self._load_all_spiders()

    def _check_name_duplicates(self) -> None:
        dupes = []
        for name, locations in self._found.items():
            dupes.extend(
                [
                    f"  {cls} named {name!r} (in {mod})"
                    for mod, cls in locations
                    if len(locations) > 1
                ]
            )

        if dupes:
            dupes_string = "\n\n".join(dupes)
            warnings.warn(
                "There are several spiders with the same name:\n\n"
                f"{dupes_string}\n\n  This can cause unexpected behavior.",
                category=UserWarning,
            )

    def _load_spiders(self, module: ModuleType) -> None:
        for spcls in iter_spider_classes(module):
            self._found[spcls.name].append((module.__name__, spcls.__name__))
            self._spiders[spcls.name] = spcls

    def _load_all_spiders(self) -> None:
        for name in self.spider_modules:
            try:
                for module in walk_modules(name):
                    self._load_spiders(module)
            except ImportError:
                if self.warn_only:
                    warnings.warn(
                        f"\n{traceback.format_exc()}Could not load spiders "
                        f"from module '{name}'. "
                        "See above traceback for details.",
                        category=RuntimeWarning,
                    )
                else:
                    raise
        self._check_name_duplicates()

    @classmethod
    def from_settings(cls, settings: BaseSettings) -> Self:
        return cls(settings)

    def load(self, spider_name: str) -> Type[Spider]:
        """
        Return the Spider class for the given spider name. If the spider
        name is not found, raise a KeyError.
        """
        try:
            return self._spiders[spider_name]
        except KeyError:
            raise KeyError(f"Spider not found: {spider_name}")

    def find_by_request(self, request: Request) -> List[str]:
        """
        Return the list of spider names that can handle the given request.
        """
        return [
            name for name, cls in self._spiders.items() if cls.handles_request(request)
        ]

    def list(self) -> List[str]:
        """
        Return a list with the names of all spiders available in the project.
        """
        return list(self._spiders.keys())
