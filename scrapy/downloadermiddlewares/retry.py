"""
An extension to retry failed requests that are potentially caused by temporary
problems such as a connection timeout or HTTP 500 error.

You can change the behaviour of this middleware by modifying the scraping settings:
RETRY_TIMES - how many times to retry a failed page
RETRY_HTTP_CODES - which HTTP response codes to retry

Failed pages are collected on the scraping process and rescheduled at the end,
once the spider has finished crawling all regular (non failed) pages.
"""
import warnings
from logging import Logger, getLogger
from typing import Optional, Type, Union

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.http.request import Request
from scrapy.settings import Settings
from scrapy.spiders import Spider
from scrapy.utils.misc import load_object
from scrapy.utils.python import global_object_name
from scrapy.utils.response import response_status_message

retry_logger = getLogger(__name__)


def backwards_compatibility_getattr(self, name):
    if name == "EXCEPTIONS_TO_RETRY":
        warnings.warn(
            "Attribute RetryMiddleware.EXCEPTIONS_TO_RETRY is deprecated. "
            "Use the RETRY_EXCEPTIONS setting instead.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return tuple(
            load_object(x) if isinstance(x, str) else x
            for x in Settings().getlist("RETRY_EXCEPTIONS")
        )
    raise AttributeError(
        f"{self.__class__.__name__!r} object has no attribute {name!r}"
    )


class BackwardsCompatibilityMetaclass(type):
    __getattr__ = backwards_compatibility_getattr


def get_retry_request(
    request: Request,
    *,
    spider: Spider,
    reason: Union[str, Exception, Type[Exception]] = "unspecified",
    max_retry_times: Optional[int] = None,
    priority_adjust: Optional[int] = None,
    logger: Logger = retry_logger,
    stats_base_key: str = "retry",
):
    """
    Returns a new :class:`~scrapy.Request` object to retry the specified
    request, or ``None`` if retries of the specified request have been
    exhausted.

    For example, in a :class:`~scrapy.Spider` callback, you could use it as
    follows::

        def parse(self, response):
            if not response.text:
                new_request_or_none = get_retry_request(
                    response.request,
                    spider=self,
                    reason='empty',
                )
                return new_request_or_none

    *spider* is the :class:`~scrapy.Spider` instance which is asking for the
    retry request. It is used to access the :ref:`settings <topics-settings>`
    and :ref:`stats <topics-stats>`, and to provide extra logging context (see
    :func:`logging.debug`).

    *reason* is a string or an :class:`Exception` object that indicates the
    reason why the request needs to be retried. It is used to name retry stats.

    *max_retry_times* is a number that determines the maximum number of times
    that *request* can be retried. If not specified or ``None``, the number is
    read from the :reqmeta:`max_retry_times` meta key of the request. If the
    :reqmeta:`max_retry_times` meta key is not defined or ``None``, the number
    is read from the :setting:`RETRY_TIMES` setting.

    *priority_adjust* is a number that determines how the priority of the new
    request changes in relation to *request*. If not specified, the number is
    read from the :setting:`RETRY_PRIORITY_ADJUST` setting.

    *logger* is the logging.Logger object to be used when logging messages

    *stats_base_key* is a string to be used as the base key for the
    retry-related job stats
    """
    settings = spider.crawler.settings
    assert spider.crawler.stats
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
        "Gave up retrying %(request)s (failed %(retry_times)d times): " "%(reason)s",
        {"request": request, "retry_times": retry_times, "reason": reason},
        extra={"spider": spider},
    )
    return None


class RetryMiddleware(metaclass=BackwardsCompatibilityMetaclass):
    def __init__(self, settings):
        if not settings.getbool("RETRY_ENABLED"):
            raise NotConfigured
        self.max_retry_times = settings.getint("RETRY_TIMES")
        self.retry_http_codes = set(
            int(x) for x in settings.getlist("RETRY_HTTP_CODES")
        )
        self.priority_adjust = settings.getint("RETRY_PRIORITY_ADJUST")

        try:
            self.exceptions_to_retry = self.__getattribute__("EXCEPTIONS_TO_RETRY")
        except AttributeError:
            # If EXCEPTIONS_TO_RETRY is not "overridden"
            self.exceptions_to_retry = tuple(
                load_object(x) if isinstance(x, str) else x
                for x in settings.getlist("RETRY_EXCEPTIONS")
            )

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_response(self, request, response, spider):
        if request.meta.get("dont_retry", False):
            return response
        if response.status in self.retry_http_codes:
            reason = response_status_message(response.status)
            return self._retry(request, reason, spider) or response
        return response

    def process_exception(self, request, exception, spider):
        if isinstance(exception, self.exceptions_to_retry) and not request.meta.get(
            "dont_retry", False
        ):
            return self._retry(request, exception, spider)

    def _retry(self, request, reason, spider):
        max_retry_times = request.meta.get("max_retry_times", self.max_retry_times)
        priority_adjust = request.meta.get("priority_adjust", self.priority_adjust)
        return get_retry_request(
            request,
            reason=reason,
            spider=spider,
            max_retry_times=max_retry_times,
            priority_adjust=priority_adjust,
        )

    __getattr__ = backwards_compatibility_getattr
