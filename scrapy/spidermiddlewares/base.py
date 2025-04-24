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

    You can override the
    :meth:`~scrapy.spidermiddlewares.base.BaseSpiderMiddleware.get_processed_request`
    method to add processing code for requests and the
    :meth:`~scrapy.spidermiddlewares.base.BaseSpiderMiddleware.get_processed_item`
    method to add processing code for items. These methods take a single
    request or item from the spider output iterable and return a request or
    item (the same or a new one), or ``None`` to remove this request or item
    from the processing.
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
        """Return a processed request from the spider output.

        This method is called with a single request from the spider output.
        It should return the same or a different request, or ``None`` to
        ignore it.

        :param request: the input request
        :type request: :class:`~scrapy.Request` object

        :param response: the response being processed
        :type response: :class:`~scrapy.http.Response` object

        :return: the processed request or ``None``
        """
        return request

    def get_processed_item(self, item: Any, response: Response) -> Any:
        """Return a processed item from the spider output.

        This method is called with a single item from the spider output.
        It should return the same or a different item, or ``None`` to
        ignore it.

        :param item: the input item
        :type item: item object

        :param response: the response being processed
        :type response: :class:`~scrapy.http.Response` object

        :return: the processed item or ``None``
        """
        return item
