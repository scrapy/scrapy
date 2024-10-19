"""
Download timeout middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy import Request, Spider, signals

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Response


class DownloadTimeoutMiddleware:
    def __init__(self, timeout: float = 180):
        self._timeout: float = timeout

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        o = cls(crawler.settings.getfloat("DOWNLOAD_TIMEOUT"))
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider: Spider) -> None:
        self._timeout = getattr(spider, "download_timeout", self._timeout)

    def process_request(
        self, request: Request, spider: Spider
    ) -> Request | Response | None:
        if self._timeout:
            request.meta.setdefault("download_timeout", self._timeout)
        return None
