from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy import Request

from .base import BaseSpiderMiddleware

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class StartSpiderMiddleware(BaseSpiderMiddleware):
    """Set :reqmeta:`is_start_request`.

    .. reqmeta:: is_start_request

    is_start_request
    ----------------

    :attr:`~scrapy.Request.meta` key that is set to ``True`` in :ref:`start
    requests <start-requests>`, allowing you to tell start requests apart from
    other requests, e.g. in :ref:`downloader middlewares
    <topics-downloader-middleware>`.
    """

    async def process_start(self, start: AsyncIterator[Any]) -> AsyncIterator[Any]:
        async for o in start:
            if isinstance(o, Request):
                o.meta.setdefault("is_start_request", True)
            yield o
