"""
DuplicatesFilterMiddleware: Filter out already visited urls
"""

from scrapy.core.exceptions import IgnoreRequest, NotConfigured
from scrapy.utils.misc import load_object
from scrapy.conf import settings

class DuplicatesFilterMiddleware(object):
    """Filter out already seen requests to avoid visiting pages more than once."""
    def __init__(self):
        clspath = settings.get('DUPEFILTER_FILTERCLASS')
        if not clspath:
            raise NotConfigured

        self.dupefilter = load_object(clspath)()

    def enqueue_request(self, domain, request):
        added = self.dupefilter.add(domain, request)
        if not (added or request.dont_filter):
            raise IgnoreRequest('Skipped (already seen request)')

    def open_domain(self, domain):
        self.dupefilter.open(domain)

    def close_domain(self, domain):
        self.dupefilter.close(domain)
