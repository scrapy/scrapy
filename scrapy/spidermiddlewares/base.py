from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy import Request, Spider

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Iterable

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Response


class BaseSpiderMiddleware:
    """Optional base class for spider middlewares.

    This class provides helper methods for asynchronous ``process_spider_output``
    methods. Middlewares that don't have a ``process_spider_output`` method don't need
    to use it.
    """

    def __init__(self, crawler: Crawler):
        self.crawler: Crawler = crawler

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def process_spider_output(
        self, response: Response, result: Iterable[Any], spider: Spider
    ) -> Iterable[Any]:
        for o in result:
            if isinstance(o, Request):
                o = self.get_processed_request(o, response)
            else:
                o = self.get_processed_item(o, response)
            if o is not None:
                yield o

    async def process_spider_output_async(
        self, response: Response, result: AsyncIterable[Any], spider: Spider
    ) -> AsyncIterable[Any]:
        async for o in result:
            if isinstance(o, Request):
                o = self.get_processed_request(o, response)
            else:
                o = self.get_processed_item(o, response)
            if o is not None:
                yield o

    def get_processed_request(
        self, request: Request, response: Response
    ) -> Request | None:
        """TODO: describe the protocol"""
        return request

    def get_processed_item(self, item: Any, response: Response) -> Any:
        """TODO: describe the protocol"""
        return item
