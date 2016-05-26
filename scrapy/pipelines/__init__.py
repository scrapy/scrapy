"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""

from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import process_chain
from scrapy.item import BaseItem

class ItemPipelineManager(MiddlewareManager):

    component_name = 'item pipeline'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return build_component_list(settings.getwithbase('ITEM_PIPELINES'))

    def _add_middleware(self, pipe):
        super(ItemPipelineManager, self)._add_middleware(pipe)
        if hasattr(pipe, 'process_item'):
            self.methods['process_item'].append(pipe.process_item)

    def process_item(self, item, spider):
        def buildPipelineHandler(func):
            def pipelineHandler(output):
                if isinstance(output, (BaseItem, dict)):
                    return func(output, spider)
            return pipelineHandler
        pipelines_list = [buildPipelineHandler(method) for method in self.methods['process_item']]
        return process_chain(pipelines_list, item)
