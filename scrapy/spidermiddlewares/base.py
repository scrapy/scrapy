from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy import Request, Spider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Response


class BaseSpiderMiddleware:
    """Optional base class for spider middlewares.

    .. versionadded:: 2.13

    This class provides helper methods for asynchronous
    ``process_spider_output()`` and ``process_start()`` methods. Middlewares
    that don't have either of these methods don't need to use this class.

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

    def process_start_requests(
        self, start: Iterable[Any], spider: Spider
    ) -> Iterable[Any]:
        for o in start:
            if (o := self._get_processed(o, None)) is not None:
                yield o

    async def process_start(self, start: AsyncIterator[Any]) -> AsyncIterator[Any]:
        async for o in start:
            if (o := self._get_processed(o, None)) is not None:
                yield o

    def process_spider_output(
        self, response: Response, result: Iterable[Any], spider: Spider
    ) -> Iterable[Any]:
        for o in result:
            if (o := self._get_processed(o, response)) is not None:
                yield o

    async def process_spider_output_async(
        self, response: Response, result: AsyncIterator[Any], spider: Spider
    ) -> AsyncIterator[Any]:
        async for o in result:
            if (o := self._get_processed(o, response)) is not None:
                yield o

    def _get_processed(self, o: Any, response: Response | None) -> Any:
        if isinstance(o, Request):
            return self.get_processed_request(o, response)
        return self.get_processed_item(o, response)

    def get_processed_request(
        self, request: Request, response: Response | None
    ) -> Request | None:
        """Return a processed request from the spider output.

        This method is called with a single request from the start seeds or the
        spider output. It should return the same or a different request, or
        ``None`` to ignore it.

        :param request: the input request
        :type request: :class:`~scrapy.Request` object

        :param response: the response being processed
        :type response: :class:`~scrapy.http.Response` object or ``None`` for
            start seeds

        :return: the processed request or ``None``
        """
        return request

    def get_processed_item(self, item: Any, response: Response | None) -> Any:
        """Return a processed item from the spider output.

        This method is called with a single item from the start seeds or the
        spider output. It should return the same or a different item, or
        ``None`` to ignore it.

        :param item: the input item
        :type item: item object

        :param response: the response being processed
        :type response: :class:`~scrapy.http.Response` object or ``None`` for
            start seeds

        :return: the processed item or ``None``
        """
        return item
