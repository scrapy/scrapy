"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""
import collections

from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import process_chain, parallel
from scrapy.item import BaseItem
from scrapy.exceptions import SplitItem

from twisted.internet.defer import DeferredList

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
            if func is not None:
                def pipelineHandler(output, *args, **kw):
                    """
                    Pipeline Handlers: Closures using pipeline functions
                    item->A->iterable->B->DeferredList->Empty handler->SplitItem
                    item->A->item->B->item->Empty handler
                    """
                    if isinstance(output, (BaseItem, dict)):
                        return func(output, spider)
                    elif isinstance(output, collections.Iterable):
                        if isinstance(output[0], tuple):
                            raise SplitItem("Item split")
                        else:
                            scraper.slot.itemproc_size += len(output) - 1
                            concurrent_items = scraper.concurrent_items
                            doneIndex = pipelines_list.index(pipelineHandler)
                            remainingList = pipelines_list[doneIndex: ]
                            dfd = parallel(output, concurrent_items, \
                                self._create_intermediate_chain, remainingList,spider)
                            return dfd
            else:
                def pipelineHandler(output, *args, **kw):
                    """
                    Empty Handler
                    Required to handle the output of the last handler, if it
                    returns an iterable.
                    item->A->iterable->Empty handler->Final handler
                    """
                    if isinstance(output, (BaseItem, dict)):
                        return output
                    elif isinstance(output, collections.Iterable):
                        if isinstance(output[0], tuple):
                            raise SplitItem("Item split")
                        else:
                            scraper.slot.itemproc_size += len(output) - 1
                            concurrent_items = scraper.concurrent_items
                            doneIndex = pipelines_list.index(pipelineHandler)
                            remainingList = pipelines_list[doneIndex: ]
                            dfd = parallel(output, concurrent_items, \
                                self._create_intermediate_chain, remainingList,spider)
                            return dfd
            return pipelineHandler
        
        def finalHandler(output, *args, **kw):
            """
            If the last pipeline returns an iterable, it's handler cannot deal with
            the result, which is why an Empty handler is uses. This final handler is
            used to deal with the result of the Empty Handler.
            """
            if isinstance(output, (BaseItem, dict)):
                return output
            elif isinstance(output, collections.Iterable):
                raise SplitItem("Item split")
        
        pipelines_list = [buildPipelineHandler(method) for method in self.methods['process_item']]
        pipelines_list.append(buildPipelineHandler(None))
        pipelines_list.append(finalHandler)
        return process_chain(pipelines_list, item)
    
    def _create_intermediate_chain(self,output, methodList, spider):
        scraper = spider.crawler.engine.scraper
        dfd = process_chain(methodList, output, spider)
        dfd.addBoth(scraper._itemproc_finished, output, None, spider)
        # Need to add scraper._itemproc_finished here, but not sure how
        # to source the necessary arguments
        # Trying with None
        return dfd
