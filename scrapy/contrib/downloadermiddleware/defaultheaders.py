"""
DefaultHeaders downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""
from scrapy import conf
from scrapy.utils.python import WeakKeyCache


class DefaultHeadersMiddleware(object):

    def __init__(self, settings=conf.settings):
        self.global_default_headers = settings.get('DEFAULT_REQUEST_HEADERS')
        self._headers = WeakKeyCache(self._default_headers)

    def _default_headers(self, spider):
        headers = dict(self.global_default_headers)
        spider_headers = getattr(spider, 'default_request_headers', None) or {}
        for k, v in spider_headers.iteritems():
            if v:
                headers[k] = v
            else:
                headers.pop(k, None)
        return headers.items()

    def process_request(self, request, spider):
        for k, v in self._headers[spider]:
            request.headers.setdefault(k, v)
