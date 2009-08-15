"""
Offsite Spider Middleware

See documentation in docs/ref/spider-middleware.rst
"""

from scrapy.http import Request
from scrapy.utils.url import url_is_from_spider

class OffsiteMiddleware(object):

    def process_spider_output(self, response, result, spider):
        return (x for x in result if not isinstance(x, Request) or \
            self.is_url_from_spider(x.url, spider))

    def is_url_from_spider(self, url, spider):
        # XXX: should we ask this to the spider manager?
        return url_is_from_spider(url, spider)
