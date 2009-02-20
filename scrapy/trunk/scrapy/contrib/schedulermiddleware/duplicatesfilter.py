"""
DuplicatesFilterMiddleware: Filter out already visited urls
"""

from scrapy.http import Request
from scrapy.conf import settings
from scrapy.core.exceptions import IgnoreRequest
from scrapy.core.filters import duplicatesfilter
from scrapy import log


class DuplicatesFilterMiddleware(object):
    """Filter out already seen requests to avoid visiting pages more than once."""

    def enqueue_request(self, domain, request, priority):
        added = duplicatesfilter.add(domain, request)
        if not (added or request.dont_filter):
            raise IgnoreRequest('Skipped (already seen request')
