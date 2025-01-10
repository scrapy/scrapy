"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import deferred_f_from_coro_f

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
            self.methods["process_item"].append(
                deferred_f_from_coro_f(pipe.process_item)
            )

    def process_item(self, item: Any, spider: Spider) -> Deferred[Any]:
        return self._process_chain("process_item", item, spider)
