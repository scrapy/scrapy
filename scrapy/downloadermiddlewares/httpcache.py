from __future__ import annotations

from email.utils import formatdate
from typing import TYPE_CHECKING

from twisted.internet import defer
from twisted.internet.error import (
    ConnectError,
    ConnectionDone,
    ConnectionLost,
    DNSLookupError,
    TCPTimedOutError,
)
from twisted.internet.error import ConnectionRefusedError as TxConnectionRefusedError
from twisted.internet.error import TimeoutError as TxTimeoutError
from twisted.web.client import ResponseFailed

from scrapy import signals
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.misc import load_object

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http.request import Request
    from scrapy.http.response import Response
    from scrapy.settings import Settings
    from scrapy.spiders import Spider
    from scrapy.statscollectors import StatsCollector


class HttpCacheMiddleware:
    DOWNLOAD_EXCEPTIONS = (
        defer.TimeoutError,
        TxTimeoutError,
        DNSLookupError,
        TxConnectionRefusedError,
        ConnectionDone,
        ConnectError,
        ConnectionLost,
        TCPTimedOutError,
        ResponseFailed,
        OSError,
    )

    crawler: Crawler

    def __init__(self, settings: Settings, stats: StatsCollector) -> None:
        if not settings.getbool("HTTPCACHE_ENABLED"):
            raise NotConfigured
        self.policy = load_object(settings["HTTPCACHE_POLICY"])(settings)
        self.storage = load_object(settings["HTTPCACHE_STORAGE"])(settings)
        self.ignore_missing = settings.getbool("HTTPCACHE_IGNORE_MISSING")
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        assert crawler.stats
        o = cls(crawler.settings, crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        o.crawler = crawler
        return o

    def spider_opened(self, spider: Spider) -> None:
        self.storage.open_spider(spider)

    def spider_closed(self, spider: Spider) -> None:
        self.storage.close_spider(spider)

    @_warn_spider_arg
    def process_request(
        self, request: Request, spider: Spider | None = None
    ) -> Request | Response | None:
        if request.meta.get("dont_cache", False):
            return None

        # Skip uncacheable requests
        if not self.policy.should_cache_request(request):
            request.meta["_dont_cache"] = True  # flag as uncacheable
            return None

        # Look for cached response and check if expired
        cachedresponse: Response | None = self.storage.retrieve_response(
            self.crawler.spider, request
        )
        if cachedresponse is None:
            self.stats.inc_value("httpcache/miss")
            if self.ignore_missing:
                self.stats.inc_value("httpcache/ignore")
                raise IgnoreRequest(f"Ignored request not in cache: {request}")
            return None  # first time request

        # Return cached response only if not expired
        cachedresponse.flags.append("cached")
        if self.policy.is_cached_response_fresh(cachedresponse, request):
            self.stats.inc_value("httpcache/hit")
            return cachedresponse

        # Keep a reference to cached response to avoid a second cache lookup on
        # process_response hook
        request.meta["cached_response"] = cachedresponse

        return None

    @_warn_spider_arg
    def process_response(
        self, request: Request, response: Response, spider: Spider | None = None
    ) -> Request | Response:
        if request.meta.get("dont_cache", False):
            return response

        # Skip cached responses and uncacheable requests
        if "cached" in response.flags or "_dont_cache" in request.meta:
            request.meta.pop("_dont_cache", None)
            return response

        # RFC2616 requires origin server to set Date header,
        # https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.18
        if "Date" not in response.headers:
            response.headers["Date"] = formatdate(usegmt=True)

        # Do not validate first-hand responses
        cachedresponse: Response | None = request.meta.pop("cached_response", None)
        if cachedresponse is None:
            self.stats.inc_value("httpcache/firsthand")
            self._cache_response(response, request)
            return response

        if self.policy.is_cached_response_valid(cachedresponse, response, request):
            self.stats.inc_value("httpcache/revalidate")
            return cachedresponse

        self.stats.inc_value("httpcache/invalidate")
        self._cache_response(response, request)
        return response

    @_warn_spider_arg
    def process_exception(
        self, request: Request, exception: Exception, spider: Spider | None = None
    ) -> Request | Response | None:
        cachedresponse: Response | None = request.meta.pop("cached_response", None)
        if cachedresponse is not None and isinstance(
            exception, self.DOWNLOAD_EXCEPTIONS
        ):
            self.stats.inc_value("httpcache/errorrecovery")
            return cachedresponse
        return None

    def _cache_response(self, response: Response, request: Request) -> None:
        if self.policy.should_cache_response(response, request):
            self.stats.inc_value("httpcache/store")
            self.storage.store_response(self.crawler.spider, request, response)
        else:
            self.stats.inc_value("httpcache/uncacheable")
