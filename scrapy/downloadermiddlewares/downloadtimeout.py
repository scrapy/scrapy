"""
Download timeout middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from scrapy import signals


class DownloadTimeoutMiddleware(object):
    """This middleware sets the download timeout for requests specified in the
    :setting:`DOWNLOAD_TIMEOUT` setting or :attr:`download_timeout`
    spider attribute.

    .. note::

        You can also set download timeout per-request using
        :reqmeta:`download_timeout` Request.meta key; this is supported
        even when DownloadTimeoutMiddleware is disabled.
    """

    def __init__(self, timeout=180):
        self._timeout = timeout

    @classmethod
    def from_crawler(cls, crawler):
        o = cls(crawler.settings.getfloat('DOWNLOAD_TIMEOUT'))
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider):
        self._timeout = getattr(spider, 'download_timeout', self._timeout)

    def process_request(self, request, spider):
        if self._timeout:
            request.meta.setdefault('download_timeout', self._timeout)
