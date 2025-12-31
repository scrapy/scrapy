"""
An extension to retry failed requests that are potentially caused by temporary
problems such as a connection timeout or HTTP 500 error.

You can change the behaviour of this middleware by modifying the scraping settings:
RETRY_TIMES - how many times to retry a failed page
RETRY_HTTP_CODES - which HTTP response codes to retry
RETRY_DELAY - how many seconds to wait before retrying  <-- NEW

Failed pages are collected on the scraping process and rescheduled at the end,
once the spider has finished crawling all regular (non-failed) pages.
"""

from __future__ import annotations

from logging import Logger, getLogger
from typing import TYPE_CHECKING
import time     # <-- NEW

from scrapy.exceptions import NotConfigured
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.misc import load_object
from scrapy.utils.python import global_object_name
from scrapy.utils.response import response_status_message


if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.http.request import Request
    from scrapy.settings import BaseSettings
    from scrapy.spiders import Spider


retry_logger = getLogger(__name__)


# ===================== NEW: moved here so it is available =====================
def get_retry_request(
    request: Request,
    *,
    spider: Spider,
    reason: str | Exception | type[Exception] = "unspecified",
    max_retry_times: int | None = None,
    priority_adjust: int | None = None,
    logger: Logger = retry_logger,
    stats_base_key: str = "retry",
) -> Request | None:
    """
    Returns a new Request object to retry the specified request,
    or None if retries are exhausted.
    """
    settings = spider.crawler.settings
    stats = spider.crawler.stats

    retry_times = request.meta.get("retry_times", 0) + 1

    if max_retry_times is None:
        max_retry_times = request.meta.get("max_retry_times")
        if max_retry_times is None:
            max_retry_times = settings.getint("RETRY_TIMES")

    if retry_times <= max_retry_times:
        logger.debug(
            "Retrying %(request)s (failed %(retry_times)d times): %(reason)s",
            {"request": request, "retry_times": retry_times, "reason": reason},
            extra={"spider": spider},
        )
        new_request: Request = request.copy()
        new_request.meta["retry_times"] = retry_times
        new_request.dont_filter = True

        if priority_adjust is None:
            priority_adjust = settings.getint("RETRY_PRIORITY_ADJUST")
        new_request.priority = request.priority + priority_adjust

        if callable(reason):
            reason = reason()

        if isinstance(reason, Exception):
            reason = global_object_name(reason.__class__)

        stats.inc_value(f"{stats_base_key}/count")
        stats.inc_value(f"{stats_base_key}/reason_count/{reason}")
        return new_request

    stats.inc_value(f"{stats_base_key}/max_reached")

    logger.error(
        "Gave up retrying %(request)s (failed %(retry_times)d times): %(reason)s",
        {"request": request, "retry_times": retry_times, "reason": reason},
        extra={"spider": spider},
    )
    return None
# ==============================================================================



class RetryMiddleware:
    crawler: Crawler

    def __init__(self, settings: BaseSettings):
        if not settings.getbool("RETRY_ENABLED"):
            raise NotConfigured
        self.max_retry_times = settings.getint("RETRY_TIMES")
        self.retry_http_codes = {int(x) for x in settings.getlist("RETRY_HTTP_CODES")}
        self.priority_adjust = settings.getint("RETRY_PRIORITY_ADJUST")
        self.exceptions_to_retry = tuple(
            load_object(x) if isinstance(x, str) else x
            for x in settings.getlist("RETRY_EXCEPTIONS")
        )
        self.retry_delay = settings.getfloat("RETRY_DELAY", 0.0)   # <-- NEW

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        o = cls(crawler.settings)
        o.crawler = crawler
        return o

    @_warn_spider_arg
    def process_response(
        self, request: Request, response: Response, spider: Spider | None = None
    ) -> Request | Response:
        if request.meta.get("dont_retry", False):
            return response
        if response.status in self.retry_http_codes:
            reason = response_status_message(response.status)
            return self._retry(request, reason) or response
        return response

    @_warn_spider_arg
    def process_exception(
        self, request: Request, exception: Exception, spider: Spider | None = None
    ) -> Request | Response | None:
        if isinstance(exception, self.exceptions_to_retry) and not request.meta.get(
            "dont_retry", False
        ):
            return self._retry(request, exception)
        return None

    def _retry(
        self, request: Request, reason: str | Exception | type[Exception]
    ) -> Request | None:
        max_retry_times = request.meta.get("max_retry_times", self.max_retry_times)
        priority_adjust = request.meta.get("priority_adjust", self.priority_adjust)

        # ---------- NEW: Wait before retrying ----------
        if self.retry_delay > 0:
            time.sleep(self.retry_delay)
        # ------------------------------------------------

        assert self.crawler.spider
        return get_retry_request(
            request,
            reason=reason,
            spider=self.crawler.spider,
            max_retry_times=max_retry_times,
            priority_adjust=priority_adjust,
        )
