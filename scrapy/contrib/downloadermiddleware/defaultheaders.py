"""
DefaultHeaders downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""


class DefaultHeadersMiddleware(object):

    def __init__(self, headers):
        self._headers = headers

    @classmethod
    def from_settings(cls, settings):
        return cls(settings.get('DEFAULT_REQUEST_HEADERS').items())

    @classmethod
    def from_crawler(cls, crawler):
        return cls.from_settings(crawler.settings)

    def process_request(self, request, spider):
        for k, v in self._headers:
            request.headers.setdefault(k, v)
