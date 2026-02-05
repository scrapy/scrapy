import warnings

from scrapy.core.downloader.handlers.http10 import HTTP10DownloadHandler
from scrapy.core.downloader.handlers.http11 import (
    HTTP11DownloadHandler as HTTPDownloadHandler,
)
from scrapy.exceptions import ScrapyDeprecationWarning

warnings.warn(
    "The scrapy.core.downloader.handlers.http module is deprecated,"
    " please import scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler"
    " instead of its deprecated alias scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
    ScrapyDeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "HTTP10DownloadHandler",
    "HTTPDownloadHandler",
]
