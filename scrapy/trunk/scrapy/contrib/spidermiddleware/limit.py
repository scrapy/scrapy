"""
RequestLimitMiddleware: Limits the scheduler request queue size. When spiders
try to schedule more than the allowed amount of requests the new requests
(returned by the spider) will be dropped.

The limit can be set using the spider attribue `requests_queue_size` or the
setting "REQUESTS_QUEUE_SIZE". If not specified (or 0), no limit will be
applied. 
"""

from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings
from scrapy.http import Request
from scrapy import log

class RequestLimitMiddleware(object):

    def __init__(self):
        self.max_queue_size = settings.getint("REQUESTS_QUEUE_SIZE")
        if not self.max_queue_size:
            raise NotConfigured

    def process_spider_output(self, response, result, spider):
        requests = []
        items = []
        for r in result:
            if isinstance(r, Request):
                requests.append(r)
            else:
                items.append(r)

        max_pending = getattr(spider, 'requests_queue_size', self.max_queue_size)
        if max_pending:
            pending_count = len(scrapyengine.scheduler.pending_requests.get(spider.domain_name, []))
            free_slots = max_pending - pending_count
            dropped_count = len(requests) - free_slots
            if dropped_count > 0:
                requests = requests[:free_slots]
                log.msg("Dropping %d request(s) because the maximum schedule size (%d) has been exceeded" % \
                        (dropped_count, max_pending), level=log.WARNING, domain=spider.domain_name)
        return requests + items
