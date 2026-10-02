"""
Downloader Middleware manager

See documentation in docs/topics/downloader-middleware.rst
"""

from __future__ import annotations

import warnings
from functools import partial, wraps
from itertools import islice
from typing import TYPE_CHECKING, Any
from weakref import WeakSet, finalize

from scrapy.exceptions import CloseSpider, ScrapyDeprecationWarning, _InvalidOutput
from scrapy.http import Request, Response
from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import (
    _process_pending_io,
    deferred_from_coro,
    ensure_awaitable,
    maybe_deferred_to_future,
)
from scrapy.utils.python import global_object_name

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from twisted.internet.defer import Deferred

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


def _get_max_active_size(settings: BaseSettings) -> int:
    deprecated_priority = settings.getpriority("SCRAPER_SLOT_MAX_ACTIVE_SIZE")
    priority = settings.getpriority("RESPONSE_MAX_ACTIVE_SIZE")
    assert deprecated_priority is not None
    assert priority is not None
    if deprecated_priority <= 0:
        return settings.getint("RESPONSE_MAX_ACTIVE_SIZE")
    if priority >= deprecated_priority:
        warnings.warn(
            "The SCRAPER_SLOT_MAX_ACTIVE_SIZE setting is deprecated and is "
            "being ignored because RESPONSE_MAX_ACTIVE_SIZE is set with an "
            "equal or higher priority. Remove SCRAPER_SLOT_MAX_ACTIVE_SIZE "
            "from your settings.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return settings.getint("RESPONSE_MAX_ACTIVE_SIZE")
    warnings.warn(
        "The SCRAPER_SLOT_MAX_ACTIVE_SIZE setting is deprecated, use "
        "RESPONSE_MAX_ACTIVE_SIZE instead.",
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    return settings.getint("SCRAPER_SLOT_MAX_ACTIVE_SIZE")


def _get_response_rough_size(settings: BaseSettings, max_active_size: int) -> int:
    if settings.get("RESPONSE_ROUGH_SIZE") is not None:
        return settings.getint("RESPONSE_ROUGH_SIZE")
    concurrency = settings.getint("CONCURRENT_REQUESTS")
    if not concurrency:
        # Unlimited concurrency: there is no bound on the number of in-flight
        # requests to spread a share of the limit over.
        return 0
    # Requests being downloaded, whose response size is unknown, may take up to
    # a quarter of the limit; the rest is for responses already in memory.
    return max_active_size // (4 * concurrency)


class DownloaderMiddlewareManager(MiddlewareManager):
    component_name = "downloader middleware"

    def __init__(self, *middlewares: Any, crawler: Crawler | None = None) -> None:
        super().__init__(*middlewares, crawler=crawler)
        assert crawler is not None
        settings = crawler.settings
        self._max_active_size: int = _get_max_active_size(settings)
        self._response_rough_size: int = _get_response_rough_size(
            settings, self._max_active_size
        )
        self._response_active_size = 0
        self._tracked_responses: WeakSet[Response] = WeakSet()
        self._rough_active_size = 0
        self._rough_sizes: dict[Request, int] = {}
        self._response_exceptions = settings.getbool(
            "DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS"
        )

    @classmethod
    def _get_mwlist_from_settings(cls, settings: BaseSettings) -> list[Any]:
        return build_component_list(
            settings.get_component_priority_dict_with_base("DOWNLOADER_MIDDLEWARES")
        )

    def _add_middleware(self, mw: Any) -> None:
        if hasattr(mw, "process_request"):
            self.methods["process_request"].append(mw.process_request)
            self._check_mw_method_spider_arg(mw.process_request)
        process_response = getattr(mw, "process_response", None)
        self.methods["process_response"].appendleft(process_response)
        if process_response is not None:
            self._check_mw_method_spider_arg(process_response)
        process_exception = getattr(mw, "process_exception", None)
        self.methods["process_exception"].appendleft(process_exception)
        if process_exception is not None:
            self._check_mw_method_spider_arg(process_exception)

    @property
    def _total_active_size(self) -> int:
        return self._response_active_size + self._rough_active_size

    def _count_rough_size(self, request: Request) -> None:
        # Counting the same request twice, which concurrent downloads of the
        # same request object would do, would leak its rough size, since only
        # one discount call can find it.
        if request in self._rough_sizes:
            return
        self._rough_sizes[request] = self._response_rough_size
        self._rough_active_size += self._response_rough_size

    def _discount_rough_size(self, request: Request) -> None:
        self._rough_active_size -= self._rough_sizes.pop(request, 0)

    def _count_response_size(self, response: Response, request: Request) -> None:
        # The actual response size replaces the rough size estimate of its
        # request.
        self._discount_rough_size(request)
        if response in self._tracked_responses:
            return
        self._tracked_responses.add(response)
        size = len(response.body)
        self._response_active_size += size
        finalize(response, partial(self._discount_response_size, size))

    def _discount_response_size(self, size: int) -> None:
        self._response_active_size -= size

    def download(
        self,
        download_func: Callable[[Request, Spider], Deferred[Response]],
        request: Request,
        spider: Spider,
    ) -> Deferred[Response | Request]:
        warnings.warn(
            "DownloaderMiddlewareManager.download() is deprecated, use download_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )

        @wraps(download_func)
        async def download_func_wrapped(request: Request) -> Response:
            return await maybe_deferred_to_future(download_func(request, spider))

        self._set_compat_spider(spider)
        return deferred_from_coro(self.download_async(download_func_wrapped, request))

    async def download_async(
        self,
        download_func: Callable[[Request], Coroutine[Any, Any, Response]],
        request: Request,
    ) -> Response | Request:

        try:
            result: Response | Request = await self._process_request(
                request, download_func
            )
        except Exception as ex:
            await _process_pending_io()
            # either returns a request or response (which we pass to process_response())
            # or reraises the exception
            result, _ = await self._process_exception(ex, request)
        return await self._process_response(result, request)

    def _handle_mw_method(self, method: Callable[..., Any], **kwargs: Any) -> Any:
        if method in self._mw_methods_requiring_spider:
            kwargs["spider"] = self._spider

        return method(**kwargs)

    async def _process_request(
        self,
        request: Request,
        download_func: Callable[[Request], Coroutine[Any, Any, Response]],
    ) -> Response | Request:
        for method in self.methods["process_request"]:
            assert method is not None
            response = await ensure_awaitable(
                self._handle_mw_method(method, request=request),
                _warn=global_object_name(method),
            )
            if response is not None and not isinstance(response, (Response, Request)):
                raise _InvalidOutput(
                    f"Middleware {method.__qualname__} must return None, Response or "
                    f"Request, got {response.__class__.__name__}"
                )
            if response:
                if isinstance(response, Response):
                    self._count_response_size(response, request)
                return response
        response = await download_func(request)
        if response is not None:
            self._count_response_size(response, request)
        return response

    async def _process_response(
        self, response: Response | Request, request: Request, index: int = 0
    ) -> Response | Request:
        if response is None:
            raise TypeError("Received None in process_response")

        methods = self.methods["process_response"]
        while index < len(methods):
            if isinstance(response, Request):
                return response
            method = methods[index]
            index += 1
            if method is None:
                continue
            try:
                result = await ensure_awaitable(
                    self._handle_mw_method(method, request=request, response=response),
                    _warn=global_object_name(method),
                )
            except Exception as ex:
                if not self._response_exceptions:
                    # CloseSpider closes the spider either way, it never
                    # reaches process_exception().
                    if not isinstance(ex, CloseSpider):
                        self._warn_response_exception(method, ex, index)
                    raise
                response, index = await self._process_exception(ex, request, index)
                continue

            if not isinstance(result, (Response, Request)):
                raise _InvalidOutput(
                    f"Middleware {method.__qualname__} must return Response or Request, "
                    f"got {type(result)}"
                )
            response = result
            if isinstance(response, Response):
                self._count_response_size(response, request)
        return response

    def _warn_response_exception(
        self, method: Callable[..., Any], exception: Exception, index: int
    ) -> None:
        """Warn that *exception*, raised by the process_response() *method* of a
        downloader middleware, will go to the process_exception() methods from
        *index* on once DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS is mandatory.

        Warn about nothing when all those methods are Scrapy's own: they are
        nothing for users to review, and RetryMiddleware, the one that acts on
        these exceptions, still lets them reach the request errback once
        retries are exhausted.
        """
        targets = [
            global_object_name(target)
            for target in islice(self.methods["process_exception"], index, None)
            if target is not None and not target.__module__.startswith("scrapy.")
        ]
        if not targets:
            return
        warnings.warn(
            f"{global_object_name(method)} raised"
            f" {global_object_name(type(exception))}. In a future Scrapy version,"
            " exceptions raised by the process_response() method of a downloader"
            " middleware will be passed to the process_exception() method of the"
            " downloader middlewares that have not processed the response yet,"
            " instead of reaching the request errback directly. Before setting the"
            " DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS setting to True to get"
            " that behavior now, make sure that this exception is handled as"
            " intended by the following methods, e.g. that an IgnoreRequest"
            " exception raised to drop a response is not retried:"
            f" {', '.join(targets)}.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )

    async def _process_exception(
        self, exception: Exception, request: Request, index: int = 0
    ) -> tuple[Response | Request, int]:
        """Let middlewares handle *exception*, starting at *index*.

        Return the result of the middleware that handled it and the index of
        the next middleware, or reraise *exception* if none handled it.
        """
        # CloseSpider asks the engine to close the spider, it is not a download
        # error for middlewares to recover from.
        if isinstance(exception, CloseSpider):
            raise exception

        methods = self.methods["process_exception"]
        while index < len(methods):
            method = methods[index]
            index += 1
            if method is None:
                continue
            response = await ensure_awaitable(
                self._handle_mw_method(method, request=request, exception=exception),
                _warn=global_object_name(method),
            )
            if response is not None and not isinstance(response, (Response, Request)):
                raise _InvalidOutput(
                    f"Middleware {method.__qualname__} must return None, Response or "
                    f"Request, got {type(response)}"
                )
            if response:
                if isinstance(response, Response):
                    self._count_response_size(response, request)
                return response, index
        raise exception
