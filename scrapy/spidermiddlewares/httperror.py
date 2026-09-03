"""
HttpError Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from scrapy import signals
from scrapy.exceptions import IgnoreRequest
from scrapy.utils._httpstatus import StatusHandling
from scrapy.utils.decorators import _warn_spider_arg

if TYPE_CHECKING:
    from collections.abc import Iterable

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


class HttpError(IgnoreRequest):
    """Raised by :class:`HttpErrorMiddleware` for a response whose status code
    is not successful and that the spider does not handle itself. See
    :setting:`HANDLE_HTTP_CODES`."""

    def __init__(self, response: Response, *args: Any, **kwargs: Any):
        #: The response that was filtered out.
        self.response: Response = response
        super().__init__(*args, **kwargs)


class HttpErrorMiddleware:
    """Filter out unsuccessful (erroneous) HTTP responses so that spiders don't
    have to deal with them, which (most of the time) imposes an overhead,
    consumes more resources, and makes the spider logic more complex."""

    crawler: Crawler

    def __init__(self, settings: BaseSettings):
        self._status_handling = StatusHandling(settings, legacy_settings=True)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        o = cls(crawler.settings)
        o.crawler = crawler
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider: Spider) -> None:
        self._status_handling.spider_opened(spider)

    @_warn_spider_arg
    def process_spider_input(
        self, response: Response, spider: Spider | None = None
    ) -> None:
        if 200 <= response.status < 300:  # common case
            return
        if self._status_handling.handles(response.status, response.meta):
            return
        raise HttpError(response, "Ignoring non-200 response")

    @_warn_spider_arg
    def process_spider_exception(
        self, response: Response, exception: Exception, spider: Spider | None = None
    ) -> Iterable[Any] | None:
        if isinstance(exception, HttpError):
            stats = self.crawler.stats
            stats.inc_value("httperror/response_ignored_count")
            stats.inc_value(
                f"httperror/response_ignored_status_count/{response.status}"
            )
            logger.info(
                "Ignoring response %(response)r: HTTP status code is not handled or not allowed",
                {"response": response},
                extra={"spider": self.crawler.spider},
            )
            return ()
        return None
