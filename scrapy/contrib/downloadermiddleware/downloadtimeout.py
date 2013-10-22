"""
Download timeout middleware

See documentation in docs/topics/downloader-middleware.rst
"""


class DownloadTimeoutMiddleware(object):

    def __init__(self, timeout=180):
        self._timeout = timeout

    @classmethod
    def from_settings(cls, settings):
        return cls(settings['DOWNLOAD_TIMEOUT'])

    @classmethod
    def from_crawler(cls, crawler):
        return cls.from_settings(crawler.settings)

    def process_request(self, request, spider):
        _timeout = getattr(spider, 'download_timeout', self._timeout)
        if _timeout:
            request.meta.setdefault('download_timeout', _timeout)
