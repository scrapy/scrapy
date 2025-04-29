from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.http import Request

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    from scrapy import Spider


class StartSpiderMiddleware:
    """Set :reqmeta:`is_start_request`.

    .. reqmeta:: is_start_request

    is_start_request
    ----------------

    :attr:`~scrapy.Request.meta` key that is set to ``True`` in :ref:`start
    requests <start-requests>`, allowing you to tell start requests apart from
    other requests, e.g. in :ref:`downloader middlewares
    <topics-downloader-middleware>`.
    """

    @staticmethod
    def _process(item_or_request: Any) -> Any:
        if isinstance(item_or_request, Request):
            item_or_request.meta.setdefault("is_start_request", True)
        return item_or_request

    async def process_start(
        self,
        start: AsyncIterator[Any],
    ) -> AsyncIterator[Any]:
        async for item_or_request in start:
            yield self._process(item_or_request)

    def process_start_requests(
        self, start: Iterable[Any], spider: Spider
    ) -> Iterable[Any]:
        for item_or_request in start:
            yield self._process(item_or_request)
