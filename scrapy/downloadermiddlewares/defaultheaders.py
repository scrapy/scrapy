"""
DefaultHeaders downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Tuple, Union

from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.http import Response
from scrapy.utils.python import without_none_values

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self


class DefaultHeadersMiddleware:
    def __init__(self, headers: Iterable[Tuple[str, str]]):
        self._headers: Iterable[Tuple[str, str]] = headers

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        headers = without_none_values(crawler.settings["DEFAULT_REQUEST_HEADERS"])
        return cls(headers.items())

    def process_request(
        self, request: Request, spider: Spider
    ) -> Union[Request, Response, None]:
        for k, v in self._headers:
            request.headers.setdefault(k, v)
        return None
