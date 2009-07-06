"""
RequestLimitMiddleware: Limits the scheduler request queue size. When spiders
try to schedule more than the allowed amount of requests the new requests
(returned by the spider) will be dropped.

The limit can be set using the spider attribue `requests_queue_size` or the
setting "REQUESTS_QUEUE_SIZE". If not specified (or 0), no limit will be
applied. 
"""
from itertools import imap
from pydispatch import dispatcher

from scrapy.core import signals
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

        self.max_pending = {}
        self.dropped_count = {}

        dispatcher.connect(self.domain_opened, signal=signals.domain_opened)
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)

    def domain_opened(self, domain, spider):
        self.max_pending[domain] = getattr(spider, 'requests_queue_size', self.max_queue_size)
        self.dropped_count[domain] = 0

    def domain_closed(self, domain):
        dropped_count = self.dropped_count[domain]
        if dropped_count:
            max_pending = self.max_pending[domain]
            log.msg('Dropped %d request(s) because the scheduler queue size limit (%d requests) was exceeded' % \
                    (dropped_count, max_pending), level=log.DEBUG, domain=domain)
        del self.dropped_count[domain]
        del self.max_pending[domain]

    def process_spider_output(self, response, result, spider):
        domain = spider.domain_name
        max_pending = self.max_pending.get(domain, 0)
        if max_pending:
            return imap(lambda v: self._limit_requests(v, domain, max_pending), result)
        else:
            return result

    def _limit_requests(self, request_or_other, domain, max_pending):
        if isinstance(request_or_other, Request):
            free_slots = max_pending - self._pending_count(domain)
            if free_slots > 0:
                # Scheduler isn't saturated and it is fine to schedule more requests.
                return request_or_other
            else:
                # Skip the request and give engine time to handle other tasks.
                self.dropped_count[domain] += 1
                return None
        else:
            # Return others (non-requests) as is.
            return request_or_other

    def _pending_count(self, domain):
        pending = scrapyengine.scheduler.pending_requests.get(domain, [])
        return len(pending)
