"""
The Scrapy Scheduler
"""

from twisted.internet import defer

from scrapy.utils.datatypes import PriorityQueue, PriorityStack
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

    def domain_is_open(self, domain):
        """Check if scheduler's resources were allocated for a domain"""
        return domain in self.pending_requests

    def domain_has_pending_requests(self, domain):
        """Check if are there pending requests for a domain"""
        if domain in self.pending_requests:
            return bool(self.pending_requests[domain])

    def open_domain(self, domain):
        """Allocates scheduling resources for the given domain"""
        Priority = PriorityStack if self.dfo else PriorityQueue
        self.pending_requests[domain] = Priority()

    def enqueue_request(self, domain, request):
        """Enqueue a request to be downloaded for a domain that is currently
        being scraped.
        """
        dfd = defer.Deferred()
        self.pending_requests[domain].push((request, dfd), request.priority)
        return dfd

    def next_request(self, domain):
        """Return the next available request to be downloaded for a domain.

        Returns a pair ``(request, deferred)`` where ``deferred`` is the
        `Deferred` instance returned to the original requester.

        ``(None, None)`` is returned if there aren't any request pending for
        the given domain.
        """
        try:
            return self.pending_requests[domain].pop()[0] # [1] is priority
        except (KeyError, IndexError):
            return (None, None)

    def close_domain(self, domain):
        """Called when a spider has finished scraping to free any resources
        associated with the domain.
        """
        self.pending_requests.pop(domain, None)

    def is_idle(self):
        """Checks if the schedulers has any request pendings"""
        return not self.pending_requests
