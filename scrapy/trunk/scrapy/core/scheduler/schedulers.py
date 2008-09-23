"""
The Scrapy Scheduler
"""

from twisted.internet import defer

from scrapy.core.scheduler.filter import GroupFilter
from scrapy.core import log
from scrapy.core.exceptions import IgnoreRequest
from scrapy.utils.datatypes import PriorityQueue, PriorityStack
from scrapy.utils.defer import defer_fail
from scrapy.conf import settings


class Scheduler(object) :
    """
    The scheduler decides what to scrape, how fast, and in what order.
    The scheduler schedules websites and pages to be scraped. Individual
    web pages that are to be scraped are batched up into a "run" for a website.
    As the domain is being scraped, pages that are discovered are added to the
    scheduler. The scheduler must not allow the same page to be requested
    multiple times within the same batch.

    Typical usage:

    * next_availble_domain() called to find out when there is something to do
    * begin_domain() called to commence scraping a website
    * enqueue_request() called multiple times when new links found
    * next_request() called multiple times when there is capacity to process urls
    * close_domain() called when there are no more pages or upon error

    Note a couple things:
    1) The order in which you get back the list of pages to scrape is not
       necesarily the order you put them in.
    2) A canonical URL is calculated for each url for each domain to check that
       it is unique, however the actual url passed in is returned when
       get_next_page is called.
       This is for two main reasons:
        * To be nice to the screen scraped site just incase the specific
          format of the url is significant.
        * To take advantage of any caching that uses the URL/URI as a key

    all_domains contains the names of all domains that are to be scheduled.

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
        self.groupfilter = GroupFilter()
        self.dfo = settings.get('SCHEDULER_ORDER', '').upper() == 'DFO'

    def domain_is_open(self, domain):
        return domain in self.pending_requests

    def is_pending(self, domain):
        return domain in self.pending_domains_count

    def domain_has_pending(self, domain):
        if domain in self.pending_requests:
            return not self.pending_requests[domain].empty()

    def next_domain(self) :
        """
        Return next domain available to scrape and remove it from available domains queue
        """
        if self.pending_domains_count:
            priority, domain = self.domains_queue.get_nowait()
            if self.pending_domains_count[domain] == 1:
                del self.pending_domains_count[domain]
            else:
                self.pending_domains_count[domain] -= 1
            return domain
        return None

    def add_domain(self, domain, priority=1):
        """
        This functions schedules a new domain to be scraped, with the given
        priority. It doesn't check if the domain is already scheduled.  A
        domain can be scheduled twice, either with the same or with different
        priority.
        """
        self.domains_queue.put(domain, priority=priority)
        if domain not in self.pending_domains_count:
            self.pending_domains_count[domain] = 1
        else:
            self.pending_domains_count[domain] += 1

    def open_domain(self, domain):
        """ 
        Allocates resources for maintaining a schedule for domain.
        """
        if self.dfo:
            self.pending_requests[domain] = PriorityStack()
        else:
            self.pending_requests[domain] = PriorityQueue()

        self.groupfilter.open(domain)

    def enqueue_request(self, domain, request, priority=1):
        """
        Add a page to be scraped for a domain that is currently being scraped.
        """
        requestid = request.fingerprint()
        added = self.groupfilter.add(domain, requestid)

        if request.dont_filter or added:
            deferred = defer.Deferred()
            self.pending_requests[domain].put((request, deferred), priority)
            return deferred
        else:
            return defer_fail(IgnoreRequest('Skipped (already visited): %s' % request))

    def request_seen(self, domain, request):
        """
        Returns True if the given Request was scheduled before for the given
        domain
        """
        return self.groupfilter.has(domain, request.fingerprint())

    def next_request(self, domain):
        """
        Get the next request to be scraped.

        None should be returned if there are no more request pending for the domain passed.
        """
        pending_list = self.pending_requests.get(domain)
        if pending_list and not pending_list.empty():
            return pending_list.get_nowait()[1]
        else:
            return (None, None)

    def close_domain(self, domain) :
        """
        Called once we are finished scraping a domain. The scheduler will
        free any resources associated with the domain.
        """
        try :
            del self.pending_requests[domain]
        except Exception, inst:
            msg = "Could not clear pending pages for domain %s, %s" % (domain, inst)
            log.msg(msg, level=log.WARNING)

        try :
            self.groupfilter.close(domain)
        except Exception, inst:
            msg = "Could not clear url filter for domain %s, %s" % (domain, inst)
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
        return not self.pending_requests
