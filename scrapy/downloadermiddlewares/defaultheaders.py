"""
DefaultHeaders downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.utils.python import without_none_values

if TYPE_CHECKING:
    from collections.abc import Iterable

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request, Spider
    from scrapy.crawler import Crawler
    from scrapy.http import Response


class DefaultHeadersMiddleware:
    def __init__(self, headers: Iterable[tuple[str, str]]):
        self._headers: Iterable[tuple[str, str]] = headers

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        headers = without_none_values(crawler.settings["DEFAULT_REQUEST_HEADERS"])
        return cls(headers.items())

    def process_request(
        self, request: Request, spider: Spider
    ) -> Request | Response | None:
        for k, v in self._headers:
            request.headers.setdefault(k, v)
        return None
