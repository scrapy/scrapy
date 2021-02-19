"""
An extension to retry failed requests that are potentially caused by temporary
problems such as a connection timeout or HTTP 500 error.

You can change the behaviour of this middleware by modifing the scraping settings:
RETRY_TIMES - how many times to retry a failed page
RETRY_HTTP_CODES - which HTTP response codes to retry

Failed pages are collected on the scraping process and rescheduled at the end,
once the spider has finished crawling all regular (non failed) pages.
"""
import logging

from twisted.internet import defer
from twisted.internet.error import (
    ConnectError,
    ConnectionDone,
    ConnectionLost,
    ConnectionRefusedError,
    DNSLookupError,
    TCPTimedOutError,
    TimeoutError,
)
from twisted.web.client import ResponseFailed

from scrapy.core.downloader.handlers.http11 import TunnelError
from scrapy.exceptions import NotConfigured
from scrapy.utils.python import global_object_name
from scrapy.utils.response import response_status_message


class RetryMiddleware:

    # IOError is raised by the HttpCompression middleware when trying to
    # decompress an empty response
    EXCEPTIONS_TO_RETRY = (defer.TimeoutError, TimeoutError, DNSLookupError,
                           ConnectionRefusedError, ConnectionDone, ConnectError,
                           ConnectionLost, TCPTimedOutError, ResponseFailed,
                           IOError, TunnelError)

    SETTING_PREFIX = ""
    META_PREFIX = ""
    STATS_PREFIX = ""

    def __init__(self, settings):
        if not settings.getbool(f"{self.SETTING_PREFIX}RETRY_ENABLED"):
            raise NotConfigured
        self.logger = logging.getLogger(__name__)
        self.max_retry_times = settings.getint(f"{self.SETTING_PREFIX}RETRY_TIMES")
        self.retry_http_codes = set(int(x) for x in settings.getlist(f"{self.SETTING_PREFIX}RETRY_HTTP_CODES"))
        self.priority_adjust = settings.getint(f"{self.SETTING_PREFIX}RETRY_PRIORITY_ADJUST")

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_response(self, request, response, spider):
        if request.meta.get(f"{self.META_PREFIX}dont_retry", False):
            return response
        if response.status in self.retry_http_codes:
            reason = response_status_message(response.status)
            return self._retry(request, reason, spider) or response
        return response

    def process_exception(self, request, exception, spider):
        if (
            isinstance(exception, self.EXCEPTIONS_TO_RETRY)
            and not request.meta.get(f"{self.META_PREFIX}dont_retry", False)
        ):
            return self._retry(request, exception, spider)

    def _retry(self, request, reason, spider):
        retries = request.meta.get(f"{self.META_PREFIX}retry_times", 0) + 1

        retry_times = self.max_retry_times

        if f"{self.META_PREFIX}max_retry_times" in request.meta:
            retry_times = request.meta[f"{self.META_PREFIX}max_retry_times"]

        if retries <= retry_times:
            self.logger.debug("Retrying %(request)s (failed %(retries)d times): %(reason)s",
                              {'request': request, 'retries': retries, 'reason': reason},
                              extra={'spider': spider})
            retryreq = request.copy()
            retryreq.meta[f"{self.META_PREFIX}retry_times"] = retries
            retryreq.dont_filter = True
            retryreq.priority = request.priority + self.priority_adjust

            if isinstance(reason, Exception):
                reason = global_object_name(reason.__class__)

            spider.crawler.stats.inc_value(f"{self.STATS_PREFIX}retry/count")
            spider.crawler.stats.inc_value(f"{self.STATS_PREFIX}retry/reason_count/{reason}")
            return retryreq
        else:
            spider.crawler.stats.inc_value(f"{self.STATS_PREFIX}retry/max_reached")
            self.logger.error("Gave up retrying %(request)s (failed %(retries)d times): %(reason)s",
                              {'request': request, 'retries': retries, 'reason': reason},
                              extra={'spider': spider})
