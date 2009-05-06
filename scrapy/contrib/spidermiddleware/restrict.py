"""
RestrictMiddleware: restricts crawling to fixed set of particular URLs
"""

from scrapy.http import Request
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings

class RestrictMiddleware(object):
    def __init__(self):
        self.allowed_urls = set(settings.getlist('RESTRICT_TO_URLS'))
        if not self.allowed_urls:
            raise NotConfigured

    def process_spider_output(self, response, result, spider):
        def _filter(r):
            if isinstance(r, Request) and r.url not in self.allowed_urls:
                return False
            return True
        return (r for r in result or () if _filter(r))

