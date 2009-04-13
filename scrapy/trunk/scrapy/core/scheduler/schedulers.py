"""
The Scrapy Scheduler
"""

from twisted.internet import defer

from scrapy import log
from scrapy.utils.datatypes import PriorityQueue, PriorityStack
from scrapy.conf import settings


class Scheduler(object) :
    """The scheduler decides what to scrape next. In other words, it defines the
    crawling order.

    The scheduler schedules websites and requests to be scraped.  Individual
    web pages that are to be scraped are batched up into a "run" for a website.

    As the domain is being scraped, pages that are discovered are added to the
    scheduler.

    Typical usage:

        * next_domain() called each time a domain slot is freed, and return
        next domain to be scraped.

        * open_domain() called to commence scraping a website

        * enqueue_request() called multiple times to enqueue new requests to be downloaded

        * next_request() called multiple times when there is capacity to download requests

        * close_domain() called when there are no more pages for a website

    Notes:

        1. The order in which you get back the list of pages to scrape is not
        necesarily the order you put them in.

    ``pending_domains_count`` contains the names of all domains that are to be scheduled.

    Two crawling orders are available by default, which can be set with the
    SCHEDULER_ORDER settings:

        * BFO - breath-first order (default). Consumes more memory than DFO but reaches
                most relevant pages faster.

        * DFO - depth-first order. Consumes less memory than BFO but usually takes
                longer to reach the most relevant pages.
    """

    def __init__(self):
        self.pending_domains_count = {}
        self.domains_queue = PriorityQueue()
        self.pending_requests = {}
        self.dfo = settings.get('SCHEDULER_ORDER', '').upper() == 'DFO'

    def domain_is_open(self, domain):
        """Check if scheduler's resources were allocated for a domain"""
        return domain in self.pending_requests

    def is_pending(self, domain):
        """Check if a domain is waiting to be scraped in domain's queue."""
        return domain in self.pending_domains_count

    def domain_has_pending(self, domain):
        """Check if are there pending requests for a domain"""
        if domain in self.pending_requests:
            return bool(self.pending_requests[domain])

    def next_domain(self) :
        """Return next domain available to scrape and remove it from available domains queue"""
        if self.pending_domains_count:
            domain, priority = self.domains_queue.pop()
            if self.pending_domains_count[domain] == 1:
                del self.pending_domains_count[domain]
            else:
                self.pending_domains_count[domain] -= 1
            return domain
        return None

    def add_domain(self, domain, priority=0):
        """This functions schedules a new domain to be scraped, with the given priority.

        It doesn't check if the domain is already scheduled.

        A domain can be scheduled twice, either with the same or with different
        priority.

        """
        self.domains_queue.push(domain, priority)
        if domain not in self.pending_domains_count:
            self.pending_domains_count[domain] = 1
        else:
            self.pending_domains_count[domain] += 1

    def open_domain(self, domain):
        """Allocates resources for maintaining a schedule for domain."""
        Priority = PriorityStack if self.dfo else PriorityQueue
        self.pending_requests[domain] = Priority()

    def enqueue_request(self, domain, request, priority=0):
        """Enqueue a request to be downloaded for a domain that is currently being scraped."""
        dfd = defer.Deferred()
        self.pending_requests[domain].push((request, dfd), priority)
        return dfd

    def next_request(self, domain):
        """Return the next available request to be downloaded for a domain.

        Returns a pair ``(request, deferred)`` where ``deferred`` is the
        `Deferred` instance returned to the original requester.

        ``(None, None)`` should be returned if there aren't requests pending
        for the domain.

        """
        try:
            # The second value is the request scheduled priority, returns the first one.
            return self.pending_requests[domain].pop()[0]
        except (KeyError, IndexError), ex:
            return (None, None)

    def close_domain(self, domain) :
        """Called once we are finished scraping a domain.

        The scheduler will free any resources associated with the domain.

        """
        try :
            del self.pending_requests[domain]
        except Exception, inst:
            msg = "Could not clear pending pages for domain %s, %s" % (domain, inst)
            log.msg(msg, level=log.WARNING)

    def remove_pending_domain(self, domain):
        """
        Remove a pending domain not yet started. If the domain was enqueued
        several times, all those instances are removed.

        Returns the number of times the domain was enqueued. 0 if domains was
        not pending.

        If domain is open (not pending) it is not removed and returns None. You
        need to call close_domain for open domains.

        """
        if not self.domain_is_open(domain):
            return self.pending_domains_count.pop(domain, 0)

    def is_idle(self):
        """Checks if the schedulers has any request pendings"""
        return not self.pending_requests
