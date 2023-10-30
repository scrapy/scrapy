from __future__ import annotations

import logging
import pprint
from collections import defaultdict, deque
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Deque,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    Union,
    cast,
)

from twisted.internet.defer import Deferred

from scrapy import Spider
from scrapy.exceptions import NotConfigured
from scrapy.settings import Settings
from scrapy.utils.defer import process_chain, process_parallel
from scrapy.utils.misc import create_instance, load_object

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)


class MiddlewareManager:
    """Base class for implementing middleware managers"""

    component_name = "foo middleware"

    def __init__(self, *middlewares: Any) -> None:
        self.middlewares = middlewares
        # Only process_spider_output and process_spider_exception can be None.
        # Only process_spider_output can be a tuple, and only until _async compatibility methods are removed.
        self.methods: Dict[
            str, Deque[Union[None, Callable, Tuple[Callable, Callable]]]
        ] = defaultdict(deque)
        for mw in middlewares:
            self._add_middleware(mw)

    @classmethod
    def _get_mwlist_from_settings(cls, settings: Settings) -> List[Any]:
        raise NotImplementedError

    @classmethod
    def from_settings(
        cls, settings: Settings, crawler: Optional[Crawler] = None
    ) -> Self:
        mwlist = cls._get_mwlist_from_settings(settings)
        middlewares = []
        enabled = []
        for clspath in mwlist:
            try:
                mwcls = load_object(clspath)
                mw = create_instance(mwcls, settings, crawler)
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

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls.from_settings(crawler.settings, crawler)

    def _add_middleware(self, mw: Any) -> None:
        if hasattr(mw, "open_spider"):
            self.methods["open_spider"].append(mw.open_spider)
        if hasattr(mw, "close_spider"):
            self.methods["close_spider"].appendleft(mw.close_spider)

    def _process_parallel(self, methodname: str, obj: Any, *args: Any) -> Deferred:
        methods = cast(Iterable[Callable], self.methods[methodname])
        return process_parallel(methods, obj, *args)

    def _process_chain(self, methodname: str, obj: Any, *args: Any) -> Deferred:
        methods = cast(Iterable[Callable], self.methods[methodname])
        return process_chain(methods, obj, *args)

    def open_spider(self, spider: Spider) -> Deferred:
        return self._process_parallel("open_spider", spider)

    def close_spider(self, spider: Spider) -> Deferred:
        return self._process_parallel("close_spider", spider)
