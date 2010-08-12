"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""

from scrapy import log
from scrapy.middleware import MiddlewareManager

class ItemPipelineManager(MiddlewareManager):

    component_name = 'item pipeline'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return settings.getlist('ITEM_PIPELINES')

    # FIXME: remove in Scrapy 0.11
    def _wrap_old_process_item(self, old):
        def new(item, spider):
            return old(spider, item)
        return new

    def _add_middleware(self, pipe):
        super(ItemPipelineManager, self)._add_middleware(pipe)
        if hasattr(pipe, 'process_item'):
            # FIXME: remove in Scrapy 0.11
            from scrapy.utils.python import get_func_args
            if get_func_args(pipe.process_item.im_func)[1] == 'spider':
                log.msg("Update %s.process_item() method to receive (item, spider) instead of (spider, item) or they will stop working on Scrapy 0.11" % pipe.__class__.__name__, log.WARNING)
                pipe.process_item = self._wrap_old_process_item(pipe.process_item)

            self.methods['process_item'].append(pipe.process_item)

    def process_item(self, item, spider):
        return self._process_chain('process_item', item, spider)
