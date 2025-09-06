"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Callable, cast

from twisted.internet.defer import Deferred, DeferredList

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import (
    deferred_from_coro,
    maybe_deferred_to_future,
    maybeDeferred_coro,
)
from scrapy.utils.python import global_object_name

if TYPE_CHECKING:
    from collections.abc import Iterable

    from twisted.python.failure import Failure

    from scrapy import Spider
    from scrapy.settings import Settings


class ItemPipelineManager(MiddlewareManager):
    component_name = "item pipeline"

    @classmethod
    def _get_mwlist_from_settings(cls, settings: Settings) -> list[Any]:
        return build_component_list(settings.getwithbase("ITEM_PIPELINES"))

    def _add_middleware(self, pipe: Any) -> None:
        if hasattr(pipe, "open_spider"):
            self.methods["open_spider"].append(pipe.open_spider)
            self._check_mw_method_spider_arg(pipe.open_spider)
        if hasattr(pipe, "close_spider"):
            self.methods["close_spider"].appendleft(pipe.close_spider)
            self._check_mw_method_spider_arg(pipe.close_spider)
        if hasattr(pipe, "process_item"):
            self.methods["process_item"].append(pipe.process_item)
            self._check_mw_method_spider_arg(pipe.process_item)

    def process_item(self, item: Any, spider: Spider) -> Deferred[Any]:
        warnings.warn(
            f"{global_object_name(type(self))}.process_item() is deprecated, use process_item_async() instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        self._set_compat_spider(spider)
        return deferred_from_coro(self.process_item_async(item))

    async def process_item_async(self, item: Any) -> Any:
        return await self._process_chain("process_item", item, add_spider=True)

    def _process_parallel(self, methodname: str) -> Deferred[list[None]]:
        methods = cast("Iterable[Callable[..., None]]", self.methods[methodname])

        def get_dfd(method: Callable[..., None]) -> Deferred[None]:
            if method in self._mw_methods_requiring_spider:
                return maybeDeferred_coro(method, self._spider)
            return maybeDeferred_coro(method)

        dfds = [get_dfd(m) for m in methods]
        d: Deferred[list[tuple[bool, None]]] = DeferredList(
            dfds, fireOnOneErrback=True, consumeErrors=True
        )
        d2: Deferred[list[None]] = d.addCallback(lambda r: [x[1] for x in r])

        def eb(failure: Failure) -> Failure:
            return failure.value.subFailure

        d2.addErrback(eb)
        return d2

    def open_spider(self, spider: Spider) -> Deferred[list[None]]:
        warnings.warn(
            f"{global_object_name(type(self))}.open_spider() is deprecated, use open_spider_async() instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        self._set_compat_spider(spider)
        return self._process_parallel("open_spider")

    async def open_spider_async(self) -> None:
        await maybe_deferred_to_future(self._process_parallel("open_spider"))

    def close_spider(self, spider: Spider) -> Deferred[list[None]]:
        warnings.warn(
            f"{global_object_name(type(self))}.close_spider() is deprecated, use close_spider_async() instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        self._set_compat_spider(spider)
        return self._process_parallel("close_spider")

    async def close_spider_async(self) -> None:
        await maybe_deferred_to_future(self._process_parallel("close_spider"))
