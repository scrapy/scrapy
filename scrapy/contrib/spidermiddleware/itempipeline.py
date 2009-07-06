"""
ItemPipelineMiddleware: feed item pipeline with scraped items
"""
from pydispatch import dispatcher

from twisted.python.failure import Failure

from scrapy.core import signals
from scrapy.core.exceptions import DontCloseDomain
from scrapy.item.pipeline import ItemPipelineManager
from scrapy.item import ScrapedItem
from scrapy.conf import settings
from scrapy import log

class ItemPipelineMiddleware(object):
    """SpiderMiddleware that sends items through a pipeline"""

    # The type of items to process by pipeline 
    ScrapedItem = ScrapedItem

    # The Pipeline Manager to use for processing these item
    ItemPipelineManager = ItemPipelineManager

    # Maximum number of items to process in parallel by this pipeline
    concurrent_limit = settings.getint('ITEMPIPELINE_CONCURRENTLIMIT', 0)

    def __init__(self):
        self.pipeline = self.ItemPipelineManager()
        dispatcher.connect(self.domain_opened, signal=signals.domain_opened)
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)
        dispatcher.connect(self.domain_idle, signal=signals.domain_idle)

    def domain_opened(self, domain):
        self.pipeline.open_domain(domain)

    def domain_closed(self, domain):
        self.pipeline.close_domain(domain)

    def domain_idle(self, domain):
        if not self.pipeline.domain_is_idle(domain):
            raise DontCloseDomain

    def process_spider_output(self, response, result, spider):
        domain = spider.domain_name
        info = self.pipeline.domaininfo[domain]

        for item_or_request in result:
            # return to engine until pipeline frees up some slots
            # TODO: this is ugly, a proper flow control mechanism should be
            # added instead
            while 0 < self.concurrent_limit <= len(info):
                yield None

            if isinstance(item_or_request, self.ScrapedItem):
                log.msg("Scraped %s in <%s>" % (item_or_request, response.request.url), \
                    domain=domain)
                signals.send_catch_log(signal=signals.item_scraped, sender=self.__class__, \
                    item=item_or_request, spider=spider, response=response)
                self.pipeline.pipe(item_or_request, spider).addBoth(self._pipeline_finished, \
                    item_or_request, spider)
                # yielding here breaks the loop and allows the engine to run
                # other tasks, such as attending IO (very important)
                yield None 
            else:
                yield item_or_request

    def _pipeline_finished(self, pipe_result, item, spider):
        # exception can only be of DropItem type here, since other exceptions
        # are caught in the Item Pipeline (item/pipeline.py)
        if isinstance(pipe_result, Failure):
            signals.send_catch_log(signal=signals.item_dropped, \
                sender=self.__class__, item=item, spider=spider, exception=pipe_result.value)
        else:
            signals.send_catch_log(signal=signals.item_passed, \
                sender=self.__class__, item=item, spider=spider, pipe_output=pipe_result)
