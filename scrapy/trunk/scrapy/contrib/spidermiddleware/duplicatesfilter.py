"""
DuplicatesFilterMiddleware: Filter out already visited urls
"""

from pydispatch import dispatcher

from scrapy.core import signals
from scrapy.http import Request
from scrapy.core.exceptions import NotConfigured, IgnoreRequest
from scrapy.utils.request import request_fingerprint
from scrapy.utils.misc import load_object
from scrapy.conf import settings
from scrapy import log


class DuplicatesFilterMiddleware(object):
    """Filter out duplicate requests to avoid visiting same page more than once.

    filter class (defined by DUPLICATESFILTER_FILTERCLASS setting) must
    inplement a simple API:

      * open(domain) called when a new domain starts

      * close(domain) called when a domain is going to be closed.

      * add(domain, request) called each time a new request needs to be tested
        looking if it is was already seen or is a new one.  This is the most
        important method for a filtering class.

    """

    def __init__(self):
        clspath = settings.get('DUPLICATESFILTER_FILTERCLASS')
        if not clspath:
            raise NotConfigured

        self.filter = load_object(clspath)()
        dispatcher.connect(self.filter.open, signals.domain_open)
        dispatcher.connect(self.filter.close, signals.domain_closed)

    def process_spider_input(self, response, spider):
        self.filter.add(spider.domain_name, response.request)

    def process_spider_output(self, response, result, spider):
        domain = spider.domain_name
        for req in result:
            if isinstance(req, Request):
                added = self.filter.add(domain, req)
                if not (added or req.dont_filter):
                    log.msg('Skipped (already processed): %s' % req, log.TRACE, domain=domain)
                    continue
            yield req


class SimplePerDomainFilter(dict):
    """Filter out a request if already seen for same domain"""

    def open(self, domain):
        """Initialize the resources needed for filtering for this domain"""
        self[domain] = set()

    def close(self, domain):
        """Remove the resources reserved for filtering for this domain"""
        del self[domain]

    def add(self, domain, request):
        """Add the fingerprint of a request to the domain set if a equivalent fingerprint has not been added.
        This method will return true if the fingerprint was added and false otherwise.
        """
        fp = request_fingerprint(request)
        if fp not in self[domain]:
            self[domain].add(fp)
            return True
        return False
