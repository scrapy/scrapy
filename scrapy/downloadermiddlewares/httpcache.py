from __future__ import annotations

import logging
from email.utils import formatdate
from typing import TYPE_CHECKING, cast
from weakref import finalize

from twisted.internet.defer import Deferred
from twisted.internet.error import ConnectError, ConnectionDone, ConnectionLost

from scrapy import signals
from scrapy.exceptions import (
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadTimeoutError,
    IgnoreRequest,
    NotConfigured,
)
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.defer import maybe_deferred_to_future
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
    from scrapy.utils.request import RequestFingerprinterProtocol


logger = logging.getLogger(__name__)


class HttpCacheMiddleware:
    DOWNLOAD_EXCEPTIONS = (
        ConnectionDone,
        ConnectError,
        ConnectionLost,
        OSError,
        DownloadTimeoutError,
        DownloadConnectionRefusedError,
        DownloadFailedError,
    )

    crawler: Crawler
    _fingerprinter: RequestFingerprinterProtocol

    def __init__(self, settings: Settings, stats: StatsCollector) -> None:
        if not settings.getbool("HTTPCACHE_ENABLED"):
            raise NotConfigured
        self.policy = load_object(settings["HTTPCACHE_POLICY"])(settings)
        self.storage = load_object(settings["HTTPCACHE_STORAGE"])(settings)
        self.ignore_missing = settings.getbool("HTTPCACHE_IGNORE_MISSING")
        self.stats = stats
        self._downloading: dict[bytes, list[Deferred[None]]] = {}

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        assert crawler.stats
        o = cls(crawler.settings, crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        o.crawler = crawler
        assert crawler.request_fingerprinter
        o._fingerprinter = crawler.request_fingerprinter
        return o

    def spider_opened(self, spider: Spider) -> None:
        self.storage.open_spider(spider)

    def spider_closed(self, spider: Spider) -> None:
        for fingerprint in list(self._downloading):
            self._wake(fingerprint)
        self.storage.close_spider(spider)

    @_warn_spider_arg
    async def process_request(
        self, request: Request, spider: Spider | None = None
    ) -> Request | Response | None:
        if request.meta.get("dont_cache", False):
            return None

        # Skip uncacheable requests
        if not self.policy.should_cache_request(request):
            request.meta["_dont_cache"] = True  # flag as uncacheable
            return None

        # Look for cached response and check if expired
        cachedresponse = self._retrieve(request)
        if cachedresponse is None and await self._wait_for_download(request):
            cachedresponse = self._retrieve(request)

        if cachedresponse is None:
            self.stats.inc_value("httpcache/miss")
            if self.ignore_missing:
                self.stats.inc_value("httpcache/ignore")
                raise IgnoreRequest(f"Ignored request not in cache: {request}")
            self._mark_downloading(request)
            return None  # first time request

        # Return cached response only if not expired
        cachedresponse.flags.append("cached")
        if self.policy.is_cached_response_fresh(cachedresponse, request):
            self.stats.inc_value("httpcache/hit")
            return cachedresponse

        # Keep a reference to cached response to avoid a second cache lookup on
        # process_response hook
        request.meta["cached_response"] = cachedresponse
        self._mark_downloading(request)

        return None

    def _retrieve(self, request: Request) -> Response | None:
        try:
            return cast(
                "Response | None",
                self.storage.retrieve_response(self.crawler.spider, request),
            )
        except Exception:
            self.stats.inc_value("httpcache/retrieve_error")
            logger.warning(
                f"Could not read the cache entry for {request}, treating it as a "
                f"cache miss.",
                exc_info=True,
                extra={"spider": self.crawler.spider},
            )
            return None

    async def _wait_for_download(self, request: Request) -> bool:
        """Block until an ongoing download of the same resource finishes, and
        return whether such a download was found."""
        fingerprint = self._fingerprinter.fingerprint(request)
        waiters = self._downloading.get(fingerprint)
        # A request already marked as downloading is the one being awaited on,
        # so making it wait would block it forever.
        if waiters is None or request.meta.get("_httpcache_downloading") == fingerprint:
            return False
        self.stats.inc_value("httpcache/wait")
        waiter: Deferred[None] = Deferred(waiters.remove)
        waiters.append(waiter)
        await maybe_deferred_to_future(waiter)
        return True

    def _mark_downloading(self, request: Request) -> None:
        fingerprint = self._fingerprinter.fingerprint(request)
        if fingerprint in self._downloading:
            return
        waiters: list[Deferred[None]] = []
        self._downloading[fingerprint] = waiters
        request.meta["_httpcache_downloading"] = fingerprint
        # Some outcomes reach neither process_response() nor
        # process_exception(), e.g. a middleware with a higher priority raising
        # from process_response(). Waking waiters up once the request object is
        # gone keeps them from blocking forever in those cases.
        finalize(request, self._wake, fingerprint, waiters)

    def _wake(
        self, fingerprint: bytes, waiters: list[Deferred[None]] | None = None
    ) -> None:
        current = self._downloading.get(fingerprint)
        if current is None or (waiters is not None and current is not waiters):
            return
        del self._downloading[fingerprint]
        while current:
            current.pop(0).callback(None)

    def _downloaded(self, request: Request) -> None:
        fingerprint = request.meta.pop("_httpcache_downloading", None)
        if fingerprint is not None:
            self._wake(fingerprint)

    @_warn_spider_arg
    def process_response(
        self, request: Request, response: Response, spider: Spider | None = None
    ) -> Request | Response:
        # Waiters are woken up only once the response has been cached, so that
        # they can read it from the cache.
        try:
            return self._process_response(request, response)
        finally:
            self._downloaded(request)

    def _process_response(self, request: Request, response: Response) -> Response:
        if request.meta.get("dont_cache", False):
            return response

        # Skip cached responses and uncacheable requests
        if "_dont_cache" in request.meta or "cached" in response.flags:
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
        self._downloaded(request)
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
