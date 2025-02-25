from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy import Request, Spider

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Iterable

    from scrapy.http import Response


class BaseSpiderMiddleware:
    """Optional base class for spider middlewares.

    This class provides helper methods for asynchronous ``process_spider_output``
    methods. Middlewares that don't have a ``process_spider_output`` method don't need
    to use it.
    """

    def process_spider_output(
        self, response: Response, result: Iterable[Any], spider: Spider
    ) -> Iterable[Any]:
        for o in result:
            if isinstance(o, Request):
                o = self._process_request(o, response, spider)
                if o is not None:
                    yield o
            else:
                o = yield self._process_item(o, response, spider)
                if o is not None:
                    yield o

    async def process_spider_output_async(
        self, response: Response, result: AsyncIterable[Any], spider: Spider
    ) -> AsyncIterable[Any]:
        async for o in result:
            if isinstance(o, Request):
                o = self._process_request(o, response, spider)
                if o is not None:
                    yield o
            else:
                o = yield self._process_item(o, response, spider)
                if o is not None:
                    yield o

    def _process_request(
        self, request: Request, response: Response, spider: Spider
    ) -> Request | None:
        """TODO: describe the protocol"""
        return request

    def _process_item(self, item: Any, response: Response, spider: Spider) -> Any:
        """TODO: describe the protocol"""
        return item
