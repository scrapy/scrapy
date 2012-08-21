"""
DefaultHeaders downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""
from scrapy.utils.python import WeakKeyCache


class DefaultHeadersMiddleware(object):

    def __init__(self, settings):
        self._headers = WeakKeyCache(self._default_headers)
        self._settings = settings

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def _default_headers(self, spider):
        return self._settings.get('DEFAULT_REQUEST_HEADERS').items()

    def process_request(self, request, spider):
        for k, v in self._headers[spider]:
            request.headers.setdefault(k, v)
