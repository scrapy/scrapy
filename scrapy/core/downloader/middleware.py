"""
Downloader Middleware manager

See documentation in docs/topics/downloader-middleware.rst
"""

from __future__ import annotations

import warnings
from functools import wraps
from typing import TYPE_CHECKING, Any, cast

from scrapy.exceptions import ScrapyDeprecationWarning, _InvalidOutput
from scrapy.http import Request, Response
from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import (
    _defer_sleep_async,
    deferred_from_coro,
    ensure_awaitable,
    maybe_deferred_to_future,
)
from scrapy.utils.python import global_object_name

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from twisted.internet.defer import Deferred

    from scrapy import Spider
    from scrapy.settings import BaseSettings


class DownloaderMiddlewareManager(MiddlewareManager):
    component_name = "downloader middleware"

    @classmethod
    def _get_mwlist_from_settings(cls, settings: BaseSettings) -> list[Any]:
        return build_component_list(settings.getwithbase("DOWNLOADER_MIDDLEWARES"))

    def _add_middleware(self, mw: Any) -> None:
        if hasattr(mw, "process_request"):
            self.methods["process_request"].append(mw.process_request)
            self._check_mw_method_spider_arg(mw.process_request)
        if hasattr(mw, "process_response"):
            self.methods["process_response"].appendleft(mw.process_response)
            self._check_mw_method_spider_arg(mw.process_response)
        if hasattr(mw, "process_exception"):
            self.methods["process_exception"].appendleft(mw.process_exception)
            self._check_mw_method_spider_arg(mw.process_exception)

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
        async def process_request(request: Request) -> Response | Request:
            for method in self.methods["process_request"]:
                method = cast("Callable", method)
                if method in self._mw_methods_requiring_spider:
                    response = await ensure_awaitable(
                        method(request=request, spider=self._spider),
                        _warn=global_object_name(method),
                    )
                else:
                    response = await ensure_awaitable(
                        method(request=request), _warn=global_object_name(method)
                    )
                if response is not None and not isinstance(
                    response, (Response, Request)
                ):
                    raise _InvalidOutput(
                        f"Middleware {method.__qualname__} must return None, Response or "
                        f"Request, got {response.__class__.__name__}"
                    )
                if response:
                    return response
            return await download_func(request)

        async def process_response(response: Response | Request) -> Response | Request:
            if response is None:
                raise TypeError("Received None in process_response")
            if isinstance(response, Request):
                return response

            for method in self.methods["process_response"]:
                method = cast("Callable", method)
                if method in self._mw_methods_requiring_spider:
                    response = await ensure_awaitable(
                        method(request=request, response=response, spider=self._spider),
                        _warn=global_object_name(method),
                    )
                else:
                    response = await ensure_awaitable(
                        method(request=request, response=response),
                        _warn=global_object_name(method),
                    )
                if not isinstance(response, (Response, Request)):
                    raise _InvalidOutput(
                        f"Middleware {method.__qualname__} must return Response or Request, "
                        f"got {type(response)}"
                    )
                if isinstance(response, Request):
                    return response
            return response

        async def process_exception(exception: Exception) -> Response | Request:
            for method in self.methods["process_exception"]:
                method = cast("Callable", method)
                if method in self._mw_methods_requiring_spider:
                    response = await ensure_awaitable(
                        method(
                            request=request, exception=exception, spider=self._spider
                        ),
                        _warn=global_object_name(method),
                    )
                else:
                    response = await ensure_awaitable(
                        method(request=request, exception=exception),
                        _warn=global_object_name(method),
                    )
                if response is not None and not isinstance(
                    response, (Response, Request)
                ):
                    raise _InvalidOutput(
                        f"Middleware {method.__qualname__} must return None, Response or "
                        f"Request, got {type(response)}"
                    )
                if response:
                    return response
            raise exception

        try:
            result: Response | Request = await process_request(request)
        except Exception as ex:
            await _defer_sleep_async()
            # either returns a request or response (which we pass to process_response())
            # or reraises the exception
            result = await process_exception(ex)
        return await process_response(result)
