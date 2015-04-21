"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""

from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list

class ItemPipelineManager(MiddlewareManager):

    component_name = 'item pipeline'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        item_pipelines = settings['ITEM_PIPELINES']
        if isinstance(item_pipelines, (tuple, list, set, frozenset)):
            from scrapy.exceptions import ScrapyDeprecationWarning
            import warnings
            warnings.warn('ITEM_PIPELINES defined as a list or a set is deprecated, switch to a dict',
                category=ScrapyDeprecationWarning, stacklevel=1)
            # convert old ITEM_PIPELINE list to a dict with order 500
            item_pipelines = dict(zip(item_pipelines, range(500, 500+len(item_pipelines))))
        return build_component_list(settings['ITEM_PIPELINES_BASE'], item_pipelines)

    def _add_middleware(self, pipe):
        super(ItemPipelineManager, self)._add_middleware(pipe)
        if hasattr(pipe, 'process_item'):
            self.methods['process_item'].append(pipe.process_item)

    def process_item(self, item, spider):
        return self._process_chain('process_item', item, spider)
