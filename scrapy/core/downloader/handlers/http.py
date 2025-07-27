from scrapy.core.downloader.handlers.http10 import HTTP10DownloadHandler
from scrapy.core.downloader.handlers.http11 import (
    HTTP11DownloadHandler as HTTPDownloadHandler,
)
from scrapy.core.downloader.handlers.httpx import HTTPXDownloadHandler

__all__ = [
    "HTTP10DownloadHandler",
    "HTTPDownloadHandler",
    "HTTPXDownloadHandler",
]
