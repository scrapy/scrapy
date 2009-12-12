"""
Request Limit Spider middleware

See documentation in docs/topics/spider-middleware.rst
"""
from itertools import imap
from scrapy.xlib.pydispatch import dispatcher

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

        dispatcher.connect(self.spider_opened, signal=signals.spider_opened)
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)

    def spider_opened(self, spider):
        self.max_pending[spider] = getattr(spider, 'requests_queue_size', self.max_queue_size)
        self.dropped_count[spider] = 0

    def spider_closed(self, spider):
        dropped_count = self.dropped_count[spider]
        if dropped_count:
            max_pending = self.max_pending[spider]
            log.msg('Dropped %d request(s) because the scheduler queue size limit (%d requests) was exceeded' % \
                    (dropped_count, max_pending), level=log.DEBUG, spider=spider)
        del self.dropped_count[spider]
        del self.max_pending[spider]

    def process_spider_output(self, response, result, spider):
        max_pending = self.max_pending.get(spider, 0)
        if max_pending:
            return imap(lambda v: self._limit_requests(v, spider, max_pending), result)
        else:
            return result

    def _limit_requests(self, request_or_other, spider, max_pending):
        if isinstance(request_or_other, Request):
            free_slots = max_pending - self._pending_count(spider)
            if free_slots > 0:
                # Scheduler isn't saturated and it is fine to schedule more requests.
                return request_or_other
            else:
                # Skip the request and give engine time to handle other tasks.
                self.dropped_count[spider] += 1
                return None
        else:
            # Return others (non-requests) as is.
            return request_or_other

    def _pending_count(self, spider):
        pending = scrapyengine.scheduler.pending_requests.get(spider, [])
        return len(pending)
