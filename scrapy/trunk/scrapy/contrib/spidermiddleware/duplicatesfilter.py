"""
DuplicatesFilterMiddleware: Filter out already visited urls
"""

from scrapy.http import Request
from scrapy.conf import settings
from scrapy.core.filters import duplicatesfilter
from scrapy import log


class DuplicatesFilterMiddleware(object):
    """Filter out already seen requests to avoid visiting pages more than once."""

    def process_spider_output(self, response, result, spider):
        domain = spider.domain_name
        for req in result:
            if isinstance(req, Request):
                has = duplicatesfilter.has(domain, req)
                if has and not req.dont_filter:
                    log.msg('Skipped (already processed): %s' % req, log.TRACE, domain=domain)
                    continue
            yield req


