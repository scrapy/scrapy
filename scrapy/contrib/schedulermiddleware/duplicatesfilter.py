"""
DuplicatesFilterMiddleware: Filter out already visited urls

See documentation in docs/topics/scheduler-middleware.rst
"""

from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.utils.misc import load_object
from scrapy.conf import settings

class DuplicatesFilterMiddleware(object):

    def __init__(self):
        clspath = settings.get('DUPEFILTER_CLASS')
        if not clspath:
            raise NotConfigured

        self.dupefilter = load_object(clspath)()

    def enqueue_request(self, spider, request):
        seen = self.dupefilter.request_seen(spider, request)
        if seen and not request.dont_filter:
            raise IgnoreRequest('Skipped (request already seen)')

    def open_spider(self, spider):
        self.dupefilter.open_spider(spider)

    def close_spider(self, spider):
        self.dupefilter.close_spider(spider)
