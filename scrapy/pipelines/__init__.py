"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""

from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import deferred_f_from_coro_f


class ItemPipelineManager(MiddlewareManager):

    component_name = 'item pipeline'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return build_component_list(settings.getwithbase('ITEM_PIPELINES'))

    def _add_middleware(self, pipe):
        super(ItemPipelineManager, self)._add_middleware(pipe)
        if hasattr(pipe, 'process_item'):
            self.methods['process_item'].append(deferred_f_from_coro_f(pipe.process_item))

    def process_item(self, item, spider):
        return self._process_chain('process_item', item, spider)
