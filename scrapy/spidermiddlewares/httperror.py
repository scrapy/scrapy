"""
HttpError Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from scrapy.exceptions import IgnoreRequest

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
    """A non-200 response was filtered"""

    def __init__(self, response: Response, *args: Any, **kwargs: Any):
        self.response = response
        super().__init__(*args, **kwargs)


class HttpErrorMiddleware:
    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings)

    def __init__(self, settings: BaseSettings):
        self.handle_httpstatus_all: bool = settings.getbool("HTTPERROR_ALLOW_ALL")
        self.handle_httpstatus_list: list[int] = settings.getlist(
            "HTTPERROR_ALLOWED_CODES"
        )

    def process_spider_input(self, response: Response, spider: Spider) -> None:
        if 200 <= response.status < 300:  # common case
            return
        meta = response.meta
        if meta.get("handle_httpstatus_all", False):
            return
        if "handle_httpstatus_list" in meta:
            allowed_statuses = meta["handle_httpstatus_list"]
        elif self.handle_httpstatus_all:
            return
        else:
            allowed_statuses = getattr(
                spider, "handle_httpstatus_list", self.handle_httpstatus_list
            )
        if response.status in allowed_statuses:
            return
        raise HttpError(response, "Ignoring non-200 response")

    def process_spider_exception(
        self, response: Response, exception: Exception, spider: Spider
    ) -> Iterable[Any] | None:
        if isinstance(exception, HttpError):
            assert spider.crawler.stats
            spider.crawler.stats.inc_value("httperror/response_ignored_count")
            spider.crawler.stats.inc_value(
                f"httperror/response_ignored_status_count/{response.status}"
            )
            logger.info(
                "Ignoring response %(response)r: HTTP status code is not handled or not allowed",
                {"response": response},
                extra={"spider": spider},
            )
            return []
        return None
