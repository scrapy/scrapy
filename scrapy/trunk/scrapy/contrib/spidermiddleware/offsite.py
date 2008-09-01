"""
OffsiteMiddleware: Filters out Requests for URLs outside the domains covered by
the spider.
"""

from scrapy.core import log
from scrapy.http import Request
from scrapy.utils.url import url_is_from_spider

class OffsiteMiddleware(object):
    def process_result(self, response, result, spider):
        def _filter(r):
            if isinstance(r, Request) and not url_is_from_spider(r.url, spider):
                log.msg("Ignoring link (offsite): %s " % r.url, level=log.DEBUG, domain=spider.domain_name)
                return False
            return True
        return (r for r in result or () if _filter(r))

