from scrapy import twisted_version
from .http10 import HTTP10DownloadHandler

if twisted_version >= (11, 1, 0):
    from .http11 import HTTP11DownloadHandler as HTTPDownloadHandler
else:
    HTTPDownloadHandler = HTTP10DownloadHandler


# backwards compatibility
class HttpDownloadHandler(HTTP10DownloadHandler):

    def __init__(self, *args, **kwargs):
        import warnings
        from scrapy.exceptions import ScrapyDeprecationWarning
        warnings.warn('HttpDownloadHandler is deprecated, import scrapy.core.downloader'
                      '.handlers.http10.HTTP10DownloadHandler instead',
                      category=ScrapyDeprecationWarning, stacklevel=1)
        super(HttpDownloadHandler, self).__init__(*args, **kwargs)
