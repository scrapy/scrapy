"""
DuplicatesFilterMiddleware: Filter out already visited urls
"""

from scrapy.core.exceptions import IgnoreRequest
from scrapy.dupefilter import dupefilter


class DuplicatesFilterMiddleware(object):
    """Filter out already seen requests to avoid visiting pages more than once."""

    def enqueue_request(self, domain, request, priority):
        added = dupefilter.add(domain, request)
        if not (added or request.dont_filter):
            raise IgnoreRequest('Skipped (already seen request')
