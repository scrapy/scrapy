"""
DefaultHeaders downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""
from scrapy.conf import settings
from scrapy.xlib.pydispatch import dispatcher
from scrapy.core import signals


class DefaultHeadersMiddleware(object):

    def __init__(self):
        self.global_default_headers = settings.get('DEFAULT_REQUEST_HEADERS')
        self._default_headers = {}
        dispatcher.connect(self.spider_opened, signal=signals.spider_opened)
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)

    def process_request(self, request, spider):
        for k, v in self._default_headers[spider].iteritems():
            if v:
                request.headers.setdefault(k, v)

    def spider_opened(self, spider):
        self._default_headers[spider] = dict(self.global_default_headers,
                **getattr(spider, 'default_request_headers', {}))

    def spider_closed(self, spider):
        self._default_headers.pop(spider)
