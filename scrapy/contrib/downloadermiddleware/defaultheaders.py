"""
DefaultHeaders downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""
from scrapy import conf
from scrapy.utils.python import WeakKeyCache


class DefaultHeadersMiddleware(object):

    def __init__(self, settings=conf.settings):
        self._headers = WeakKeyCache(self._default_headers)

    def _default_headers(self, spider):
        return spider.settings.get('DEFAULT_REQUEST_HEADERS').items()

    def process_request(self, request, spider):
        for k, v in self._headers[spider]:
            request.headers.setdefault(k, v)
