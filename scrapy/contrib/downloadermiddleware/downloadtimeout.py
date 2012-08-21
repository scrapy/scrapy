"""
Download timeout middleware

See documentation in docs/topics/downloader-middleware.rst
"""
from scrapy.utils.python import WeakKeyCache


class DownloadTimeoutMiddleware(object):

    def __init__(self, timeout=180):
        self._cache = WeakKeyCache(self._download_timeout)
        self._timeout = timeout

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings['DOWNLOAD_TIMEOUT'])

    def _download_timeout(self, spider):
        if hasattr(spider, 'download_timeout'):
            return spider.download_timeout
        return self._timeout

    def process_request(self, request, spider):
        timeout = self._cache[spider]
        if timeout:
            request.meta.setdefault('download_timeout', timeout)
