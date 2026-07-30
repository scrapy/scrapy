from __future__ import annotations

import traceback
import warnings
from collections import defaultdict
from typing import TYPE_CHECKING, Protocol, cast

# working around https://github.com/sphinx-doc/sphinx/issues/10400
from scrapy import Request, Spider  # noqa: TC001
from scrapy.utils.misc import load_object, walk_modules_iter
from scrapy.utils.spider import iter_spider_classes

if TYPE_CHECKING:
    from types import ModuleType

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.settings import BaseSettings


def get_spider_loader(settings: BaseSettings) -> SpiderLoaderProtocol:
    """Get SpiderLoader instance from settings"""
    cls_path = settings.get("SPIDER_LOADER_CLASS")
    loader_cls = load_object(cls_path)
    return cast("SpiderLoaderProtocol", loader_cls.from_settings(settings.frozencopy()))


class SpiderLoaderProtocol(Protocol):
    """Protocol for spider loader implementations.

    See :setting:`SPIDER_LOADER_CLASS`.
    """

    @classmethod
    def from_settings(cls, settings: BaseSettings) -> Self:
        """Return an instance of the class for the given settings."""

    def load(self, spider_name: str) -> type[Spider]:
        """Return the spider class for the given spider name. If the spider
        name is not found, it must raise a :exc:`KeyError`."""

    def list(self) -> list[str]:
        """Return a list with the names of all spiders available in the
        project."""

    def find_by_request(self, request: Request) -> __builtins__.list[str]:
        """Return the list of spiders names that can handle the given request."""


class SpiderLoader:
    """
    SpiderLoader is a class which locates and loads spiders
    in a Scrapy project.
    """

    def __init__(self, settings: BaseSettings):
        self.spider_modules: list[str] = settings.getlist("SPIDER_MODULES")
        self.warn_only: bool = settings.getbool("SPIDER_LOADER_WARN_ONLY")
        self._spiders: dict[str, type[Spider]] = {}
        self._found: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)
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
                stacklevel=2,
                category=UserWarning,
            )

    def _load_spiders(self, module: ModuleType) -> None:
        for spcls in iter_spider_classes(module):
            self._found[spcls.name].append((module.__name__, spcls.__name__))
            self._spiders[spcls.name] = spcls

    def _load_all_spiders(self) -> None:
        for name in self.spider_modules:
            try:
                for module in walk_modules_iter(name):
                    self._load_spiders(module)
            except (ImportError, SyntaxError):
                if self.warn_only:
                    warnings.warn(
                        f"\n{traceback.format_exc()}Could not load spiders "
                        f"from module '{name}'. "
                        "See above traceback for details.",
                        stacklevel=2,
                        category=RuntimeWarning,
                    )
                else:
                    raise
        self._check_name_duplicates()

    @classmethod
    def from_settings(cls, settings: BaseSettings) -> Self:
        """Create an instance of the class.

        It's called with the current project settings, and it loads the spiders
        found recursively in the modules of the :setting:`SPIDER_MODULES`
        setting.
        """
        return cls(settings)

    def load(self, spider_name: str) -> type[Spider]:
        """Return the spider class for the given spider name.

        If the spider name is not found, raise a :exc:`KeyError`.
        """
        try:
            return self._spiders[spider_name]
        except KeyError:
            raise KeyError(f"Spider not found: {spider_name}") from None

    def find_by_request(self, request: Request) -> list[str]:
        """
        Return the list of spider names that can handle the given request.

        It will try to match the request's url against the domains of
        the spiders.
        """
        return [
            name for name, cls in self._spiders.items() if cls.handles_request(request)
        ]

    def list(self) -> list[str]:
        """Return a list with the names of all spiders available in the project."""
        return list(self._spiders.keys())


class DummySpiderLoader:
    """A dummy spider loader that does not load any spiders."""

    @classmethod
    def from_settings(cls, settings: BaseSettings) -> Self:
        return cls()

    def load(self, spider_name: str) -> type[Spider]:
        raise KeyError("DummySpiderLoader doesn't load any spiders")

    def list(self) -> list[str]:
        return []

    def find_by_request(self, request: Request) -> __builtins__.list[str]:
        return []
