"""
Url Filter Middleware

See documentation in docs/refs/spider-middleware.rst
"""

from scrapy.http import Request
from scrapy.utils.url import canonicalize_url

class UrlFilterMiddleware(object):
    def process_spider_output(self, response, result, spider):
        disabled = getattr(spider, 'urlfilter_disabled', False)
        for r in result:
            if isinstance(r, Request) and not disabled:
                curl = canonicalize_url(r.url)
                # only assign if different to avoid re-calculating fingerprint
                if curl != r.url: 
                    r.url = curl
            yield r
