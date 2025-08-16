"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.python import global_object_name

if TYPE_CHECKING:
    from twisted.internet.defer import Deferred

    from scrapy import Spider
    from scrapy.settings import Settings


class ItemPipelineManager(MiddlewareManager):
    component_name = "item pipeline"

    @classmethod
    def _get_mwlist_from_settings(cls, settings: Settings) -> list[Any]:
        return build_component_list(settings.getwithbase("ITEM_PIPELINES"))

    def _add_middleware(self, pipe: Any) -> None:
        super()._add_middleware(pipe)
        if hasattr(pipe, "process_item"):
            self.methods["process_item"].append(pipe.process_item)

    def process_item(self, item: Any, spider: Spider | None = None) -> Deferred[Any]:
        if spider:
            self._set_compat_spider(spider)
        warnings.warn(
            f"{global_object_name(type(self))}.process_item() is deprecated, use process_item_async() instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(self.process_item_async(item))

    async def process_item_async(self, item: Any) -> Any:
        return await self._process_chain("process_item", item, self._spider)
