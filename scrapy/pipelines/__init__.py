"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""
import collections
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
        pipelines_list = []
        scraper = spider.crawler.engine.scraper
        def buildPipelineHandler(func):
            def pipelineHandler(output):
                print pipelines_list.index(pipelineHandler)
                if isinstance(output, (BaseItem, dict)):
                    return func(output, spider)
                elif isinstance(output, collections.Iterable):
                    if isinstance(output[0],tuple):
                        '''
                            Returned from a DeferredList, so raise a SplitItemError 
                            & end callchain
                        '''
                        pass
                    else:
                        '''
                            Process iterable of items
                        '''
                        scraper.slot.itemproc_size += len(output) - 1
                        concurrent_items = scraper.concurrent_items
                        doneIndex = pipelines_list.index(pipelineHandler)
                        remainingList = pipelines_list[doneIndex: ]
                        dfd = parallel(output, self.concurrent_items,
            self._create_intermediate_chain, remainingList, errback, spider)
                        return dfd
            return pipelineHandler
        pipelines_list = [buildPipelineHandler(method) for method in self.methods['process_item']]
        return process_chain(pipelines_list, item)
    
    def _create_intermediate_chain(self,output, methodList, errback, spider)
        dfd = process_chain(methodList, output, spider)
        dfd.addBoth(errback)
        # Need to add scraper._itemproc_finished here, but not sure how
        # to source the necessary arguments
        return dfd
