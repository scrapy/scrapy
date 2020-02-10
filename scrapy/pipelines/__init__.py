"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""

from warnings import warn

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import deferred_f_from_coro_f


class ItemPipelineManager(MiddlewareManager):

    component_name = 'item pipeline'

    _close_spider_order_values = {'asc', 'desc'}

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return build_component_list(settings.getwithbase('ITEM_PIPELINES'))

    @classmethod
    def from_settings(cls, settings, crawler=None):
        middleware_list = cls._get_mwlist_from_settings(settings)
        middlewares = cls._load_middlewares(middleware_list, settings, crawler)
        return cls(*middlewares, settings=settings)

    def __init__(self, *middlewares, settings):
        self._close_spider_order = settings.get('ITEM_PIPELINE_CLOSE_SPIDER_ORDER')
        if self._close_spider_order is None:
            warn("The default value of the ITEM_PIPELINE_CLOSE_SPIDER_ORDER "
                 "setting will change from 'desc' to 'asc' in a future "
                 "version of Scrapy. To remove this warning, give the "
                 "ITEM_PIPELINE_CLOSE_SPIDER_ORDER setting a explicit value.",
                 ScrapyDeprecationWarning)
            self._close_spider_order = 'desc'
        if self._close_spider_order not in self._close_spider_order_values:
            raise ValueError(
                'Invalid ITEM_PIPELINE_CLOSE_SPIDER_ORDER value: {}. '
                'Valid values: {}.'.format(
                    repr(self._close_spider_order),
                    ', '.join(
                        repr(value)
                        for value in sorted(self._close_spider_order_values)
                    ),
                )
            )
        super().__init__(*middlewares)

    def _add_middleware(self, pipe):
        if hasattr(pipe, 'open_spider'):
            self.methods['open_spider'].append(pipe.open_spider)
        if hasattr(pipe, 'process_item'):
            self.methods['process_item'].append(deferred_f_from_coro_f(pipe.process_item))
        if hasattr(pipe, 'close_spider'):
            if self._close_spider_order == 'asc':
                self.methods['close_spider'].append(pipe.close_spider)
            else:
                assert self._close_spider_order == 'desc'
                self.methods['close_spider'].appendleft(pipe.close_spider)

    def process_item(self, item, spider):
        return self._process_chain('process_item', item, spider)
