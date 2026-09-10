from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.spidermiddlewares.base import BaseSpiderMiddleware

if TYPE_CHECKING:
    from scrapy.http import Request, Response


class SessionsSpiderMiddleware(BaseSpiderMiddleware):
    """Bind requests from a spider callback to the :ref:`session <sessions>` of
    the request whose response reached that callback.

    .. versionadded:: VERSION

    Requests that set the :reqmeta:`session` request meta key themselves keep
    their own session.
    """

    def get_processed_request(
        self, request: Request, response: Response | None
    ) -> Request | None:
        if (
            response is not None
            and "session" not in request.meta
            and "session" in response.meta
        ):
            request.meta["session"] = response.meta["session"]
        return request
