"""
The Scrapy Scheduler
"""

from twisted.internet import defer
from twisted.python.failure import Failure

from scrapy.utils.datatypes import PriorityQueue, PriorityStack
from scrapy.core.schedulermw import SchedulerMiddlewareManager
from scrapy.core.exceptions import IgnoreRequest
from scrapy.conf import settings

class Scheduler(object):
    """The scheduler decides what to scrape next. In other words, it defines the
    crawling order. The scheduler schedules websites and requests to be
    scraped. Individual web pages that are to be scraped are batched up into a
    "run" for a website. New pages discovered through the crawling process are
    also added to the scheduler.
    """

    def __init__(self):
        self.pending_requests = {}
        self.dfo = settings['SCHEDULER_ORDER'].upper() == 'DFO'
        self.middleware = SchedulerMiddlewareManager()

    def spider_is_open(self, spider):
        """Check if scheduler's resources were allocated for a spider"""
        return spider in self.pending_requests

    def spider_has_pending_requests(self, spider):
        """Check if are there pending requests for a spider"""
        if spider in self.pending_requests:
            return bool(self.pending_requests[spider])

    def open_spider(self, spider):
        """Allocates scheduling resources for the given spider"""
        if spider in self.pending_requests:
            raise RuntimeError('Scheduler spider already opened: %s' % spider)

        Priority = PriorityStack if self.dfo else PriorityQueue
        self.pending_requests[spider] = Priority()
        self.middleware.open_spider(spider)

    def close_spider(self, spider):
        """Called when a spider has finished scraping to free any resources
        associated with the spider.
        """
        if spider not in self.pending_requests:
            raise RuntimeError('Scheduler spider is not open: %s' % spider)
        self.middleware.close_spider(spider)
        self.pending_requests.pop(spider, None)

    def enqueue_request(self, spider, request):
        """Enqueue a request to be downloaded for a spider that is currently being scraped."""
        return self.middleware.enqueue_request(self._enqueue_request, spider, request)

    def _enqueue_request(self, spider, request):
        dfd = defer.Deferred()
        self.pending_requests[spider].push((request, dfd), -request.priority)
        return dfd

    def clear_pending_requests(self, spider):
        """Remove all pending requests for the given spider"""
        q = self.pending_requests[spider]
        while q:
            _, dfd = q.pop()[0]
            dfd.errback(Failure(IgnoreRequest()))

    def next_request(self, spider):
        """Return the next available request to be downloaded for a spider.

        Returns a pair ``(request, deferred)`` where ``deferred`` is the
        `Deferred` instance returned to the original requester.

        ``(None, None)`` is returned if there aren't any request pending for
        the given spider.
        """
        try:
            return self.pending_requests[spider].pop()[0] # [1] is priority
        except (KeyError, IndexError):
            return (None, None)

    def is_idle(self):
        """Checks if the schedulers has any request pendings"""
        return not self.pending_requests
