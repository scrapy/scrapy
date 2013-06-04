from scrapy import optional_features
from .http10 import HTTP10DownloadHandler

if 'http11' in optional_features:
    from .http11 import HTTP11DownloadHandler as HTTPDownloadHandler
else:
    HTTPDownloadHandler = HTTP10DownloadHandler


# backwards compatibility
HttpDownloadHandler = HTTP10DownloadHandler
