"""
Restrict Spider Middleware

See documentation in docs/ref/spider-middleware.rst
"""

from itertools import ifilter

from scrapy.http import Request
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings

class RestrictMiddleware(object):
    def __init__(self):
        self.allowed_urls = set(settings.getlist('RESTRICT_TO_URLS'))
        if not self.allowed_urls:
            raise NotConfigured

    def process_spider_output(self, response, result, spider):
        return ifilter(lambda r: isinstance(r, Request) \
            and r.url not in self.allowed_urls, result or ())

