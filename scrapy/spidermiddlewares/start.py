from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseSpiderMiddleware

if TYPE_CHECKING:
    from scrapy.http import Request
    from scrapy.http.response import Response


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

    def get_processed_request(
        self, request: Request, response: Response | None
    ) -> Request | None:
        if response is None:
            request.meta.setdefault("is_start_request", True)
        return request
