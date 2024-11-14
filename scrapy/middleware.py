from __future__ import annotations

import logging
import pprint
import warnings
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any, TypeVar, cast

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.utils.defer import process_chain, process_parallel
from scrapy.utils.misc import build_from_crawler, load_object

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
_T2 = TypeVar("_T2")


class MiddlewareManager:
    """Base class for implementing middleware managers"""

    component_name = "foo middleware"

    def __init__(self, *middlewares: Any) -> None:
        self.middlewares = middlewares
        # Only process_spider_output and process_spider_exception can be None.
        # Only process_spider_output can be a tuple, and only until _async compatibility methods are removed.
        self.methods: dict[str, deque[Callable | tuple[Callable, Callable] | None]] = (
            defaultdict(deque)
        )
        for mw in middlewares:
            self._add_middleware(mw)

    @classmethod
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
        return cast(_T, instance)

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
        return cls(*middlewares)

    def _add_middleware(self, mw: Any) -> None:
        if hasattr(mw, "open_spider"):
            self.methods["open_spider"].append(mw.open_spider)
        if hasattr(mw, "close_spider"):
            self.methods["close_spider"].appendleft(mw.close_spider)

    def _process_parallel(
        self, methodname: str, obj: _T, *args: Any
    ) -> Deferred[list[_T2]]:
        methods = cast(
            "Iterable[Callable[Concatenate[_T, _P], _T2]]", self.methods[methodname]
        )
        return process_parallel(methods, obj, *args)

    def _process_chain(self, methodname: str, obj: _T, *args: Any) -> Deferred[_T]:
        methods = cast(
            "Iterable[Callable[Concatenate[_T, _P], _T]]", self.methods[methodname]
        )
        return process_chain(methods, obj, *args)

    def open_spider(self, spider: Spider) -> Deferred[list[None]]:
        return self._process_parallel("open_spider", spider)

    def close_spider(self, spider: Spider) -> Deferred[list[None]]:
        return self._process_parallel("close_spider", spider)
