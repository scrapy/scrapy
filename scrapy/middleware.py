from __future__ import annotations

import logging
import pprint
import warnings
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any, TypeVar, cast

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.utils.defer import ensure_awaitable
from scrapy.utils.deprecate import argument_is_required
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.python import global_object_name

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from twisted.internet.defer import Deferred

    # typing.Concatenate and typing.ParamSpec require Python 3.10
    # typing.Self requires Python 3.11
    from typing_extensions import Concatenate, ParamSpec, Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings, Settings

    _P = ParamSpec("_P")


logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class MiddlewareManager(ABC):
    """Base class for implementing middleware managers"""

    component_name: str
    _compat_spider: Spider | None = None

    def __init__(self, *middlewares: Any, crawler: Crawler | None = None) -> None:
        self.crawler: Crawler | None = crawler
        if crawler is None:
            warnings.warn(
                f"MiddlewareManager.__init__() was called without the crawler argument"
                f" when creating {global_object_name(self.__class__)}."
                f" This is deprecated and the argument will be required in future Scrapy versions.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
        self.middlewares: tuple[Any, ...] = middlewares
        # Only process_spider_output and process_spider_exception can be None.
        # Only process_spider_output can be a tuple, and only until _async compatibility methods are removed.
        self.methods: dict[str, deque[Callable | tuple[Callable, Callable] | None]] = (
            defaultdict(deque)
        )
        self._mw_methods_requiring_spider: set[Callable] = set()
        for mw in middlewares:
            self._add_middleware(mw)

    @property
    def _spider(self) -> Spider:
        if self.crawler is not None:
            if self.crawler.spider is None:
                raise ValueError(
                    f"{type(self).__name__} needs to access self.crawler.spider but it is None."
                )
            return self.crawler.spider
        if self._compat_spider is not None:
            return self._compat_spider
        raise ValueError(f"{type(self).__name__} has no known Spider instance.")

    def _set_compat_spider(self, spider: Spider | None) -> None:
        if spider is None or self.crawler is not None:
            return
        # printing a deprecation warning is the caller's responsibility
        if self._compat_spider is None:
            self._compat_spider = spider
        elif self._compat_spider is not spider:
            raise RuntimeError(
                f"Different instances of Spider were passed to {type(self).__name__}:"
                f" {self._compat_spider} and {spider}"
            )

    def _warn_spider_arg(self, method_name: str) -> None:
        if self.crawler:
            msg = (
                f"Passing a spider argument to {type(self).__name__}.{method_name}() is deprecated"
                " and the passed value is ignored."
            )
        else:
            msg = (
                f"Passing a spider argument to {type(self).__name__}.{method_name}() is deprecated,"
                f" {type(self).__name__} should be instantiated with a Crawler instance instead."
            )
        warnings.warn(msg, category=ScrapyDeprecationWarning, stacklevel=3)

    @classmethod
    @abstractmethod
    def _get_mwlist_from_settings(cls, settings: Settings) -> list[Any]:
        raise NotImplementedError

    @staticmethod
    def _build_from_settings(objcls: type[_T], settings: BaseSettings) -> _T:
        if hasattr(objcls, "from_settings"):
            instance = objcls.from_settings(settings)  # type: ignore[attr-defined]
            method_name = "from_settings"
        else:
            instance = objcls()
            method_name = "__new__"
        if instance is None:
            raise TypeError(f"{objcls.__qualname__}.{method_name} returned None")
        return cast("_T", instance)

    @classmethod
    def from_settings(cls, settings: Settings, crawler: Crawler | None = None) -> Self:
        warnings.warn(
            f"{cls.__name__}.from_settings() is deprecated, use from_crawler() instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return cls._from_settings(settings, crawler)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls._from_settings(crawler.settings, crawler)

    @classmethod
    def _from_settings(cls, settings: Settings, crawler: Crawler | None = None) -> Self:
        mwlist = cls._get_mwlist_from_settings(settings)
        middlewares = []
        enabled = []
        for clspath in mwlist:
            try:
                mwcls = load_object(clspath)
                if crawler is not None:
                    mw = build_from_crawler(mwcls, crawler)
                else:
                    mw = MiddlewareManager._build_from_settings(mwcls, settings)
                middlewares.append(mw)
                enabled.append(clspath)
            except NotConfigured as e:
                if e.args:
                    logger.warning(
                        "Disabled %(clspath)s: %(eargs)s",
                        {"clspath": clspath, "eargs": e.args[0]},
                        extra={"crawler": crawler},
                    )

        logger.info(
            "Enabled %(componentname)ss:\n%(enabledlist)s",
            {
                "componentname": cls.component_name,
                "enabledlist": pprint.pformat(enabled),
            },
            extra={"crawler": crawler},
        )
        return cls(*middlewares, crawler=crawler)

    def _add_middleware(self, mw: Any) -> None:  # noqa: B027
        pass

    def _check_mw_method_spider_arg(self, method: Callable) -> None:
        if argument_is_required(method, "spider"):
            warnings.warn(
                f"{method.__qualname__}() requires a spider argument,"
                f" this is deprecated and the argument will not be passed in future Scrapy versions."
                f" If you need to access the spider instance you can save the crawler instance"
                f" passed to from_crawler() and use its spider attribute.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
            self._mw_methods_requiring_spider.add(method)

    async def _process_chain(
        self,
        methodname: str,
        obj: _T,
        *args: Any,
        add_spider: bool = False,
        always_add_spider: bool = False,
    ) -> _T:
        methods = cast(
            "Iterable[Callable[Concatenate[_T, _P], _T]]", self.methods[methodname]
        )
        for method in methods:
            if always_add_spider or (
                add_spider and method in self._mw_methods_requiring_spider
            ):
                obj = await ensure_awaitable(method(obj, *(*args, self._spider)))
            else:
                obj = await ensure_awaitable(method(obj, *args))
        return obj

    def open_spider(self, spider: Spider) -> Deferred[list[None]]:  # pragma: no cover
        raise NotImplementedError(
            "MiddlewareManager.open_spider() is no longer implemented"
            " and will be removed in a future Scrapy version."
        )

    def close_spider(self, spider: Spider) -> Deferred[list[None]]:  # pragma: no cover
        raise NotImplementedError(
            "MiddlewareManager.close_spider() is no longer implemented"
            " and will be removed in a future Scrapy version."
        )
