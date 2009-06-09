"""
OffsiteMiddleware: Filters out Requests for URLs outside the domains covered by
the spider.
"""

from itertools import ifilter

from scrapy.item import ScrapedItem
from scrapy.utils.url import url_is_from_spider

class OffsiteMiddleware(object):

    def process_spider_output(self, response, result, spider):
        filter = lambda x: isinstance(x, ScrapedItem) or url_is_from_spider(x.url, spider)
        return ifilter(filter, result or ())
