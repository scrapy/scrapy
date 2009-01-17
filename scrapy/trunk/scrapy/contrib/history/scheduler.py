"""
WARNING: This Scheduler code is obsolete and needs to be rewritten 
"""

import hashlib
from datetime import datetime

from twisted.internet import defer

from scrapy import log
from scrapy.core.scheduler import Scheduler
from scrapy.core.exceptions import IgnoreRequest
from scrapy.utils.request import request_fingerprint

class RulesScheduler(Scheduler):
    """Scheduler that uses rules to determine if we should follow links

     TODO:
     * take into account where in chain of links we are (less depth should
       be crawled more often)
     * Be more strict about scraping product pages that rarely lead to new
       versions of products. The same applies to pages with links. Particularly
       useful for filtering out when there are many urls for the same product.
       (but be careful to also filter out pages that almost always lead to new
       output).
    """

    # if these parameters change, then update bin/unavailable.py

    # How often we should re-check links we know about
    MIN_CHECK_DAYS = 4

    # How often we should process pages that have not changed (need to include depth)
    MIN_PROCESS_UNCHANGED_DAYS = 12

    def enqueue_request(self, domain, request, priority=1):
        """Add a page to be scraped for a domain that is currently being scraped.

        The url will only be added if we have not checked it already within
        a specified time period.
        """
        requestid = request_fingerprint(request)
        added = self.groupfilter.add(domain, requestid)

        if request.dont_filter or added:
            key = urlkey(request.url) # we can not use fingerprint unless lost crawled history
            status = self.historydata.status(domain, key)
            now = datetime.now()
            version = None
            if status:
                _url, version, last_checked = status
                d = now - last_checked
                if d.days < self.MIN_CHECK_DAYS:
                    log.msg("Not scraping %s (scraped %s ago)" % (request.url, d), level=log.DEBUG)
                    return
            # put the version in the pending pages to avoid querying DB again
            record = (request, version, now)
            self.pending_requests[domain].put(record, priority)

    def next_request(self, domain):
        """Get the next page from the superclass. This will add a callback
        to prevent processing the page unless its content has been
        changed.

        In the event that it a page is not processed, the record_visit method
        is called to update the last_checked time.
        """
        pending_list = self.pending_requests.get(domain)
        if not pending_list :
            return None
        request, version, timestamp = pending_list.get_nowait()[1]
        post_version = hash(request.body)

        def callback(pagedata):
            """process other callback if we pass the checks"""
            
            if version == self.get_version(pagedata):
                hist = self.historydata.version_info(domain, version)
                if hist:
                    versionkey, created = hist
                    # if versionkey != urlkey(url) this means
                    # the same content is available on a different url
                    delta = timestamp - created
                    if delta.days < self.MIN_PROCESS_UNCHANGED_DAYS:
                        message = "skipping %s: unchanged for %s" % (pagedata.url, delta)
                        raise IgnoreRequest(message)
            self.record_visit(domain, request.url, pagedata.url,
                              pagedata.parent,  self.get(pagedata),
                              post_version)
            return pagedata

        def errback(error) :
            self.record_visit(domain, request.url, request.url, None, None,
                              post_version)
            return error

        d = defer.Deferred()
        d.addCallbacks(callback, errback)
        # prepend_callback Request method was removed (it never worked properly anyways) 
        #request.prepend_callback(d)

        return request

    def get_version(self, response):
        key = hashlib.sha1(response.body.to_string()).hexdigest()
