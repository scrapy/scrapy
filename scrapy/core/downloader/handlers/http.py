from __future__ import absolute_import
from .http10 import HTTP10DownloadHandler
from .http11 import HTTP11DownloadHandler as HTTPDownloadHandler


# backwards compatibility
class HttpDownloadHandler(HTTP10DownloadHandler):

    def __init__(self, *args, **kwargs):
        import warnings
        from scrapy.exceptions import ScrapyDeprecationWarning
        warnings.warn('HttpDownloadHandler is deprecated, import scrapy.core.downloader'
                      '.handlers.http10.HTTP10DownloadHandler instead',
                      category=ScrapyDeprecationWarning, stacklevel=1)
        super(HttpDownloadHandler, self).__init__(*args, **kwargs)
