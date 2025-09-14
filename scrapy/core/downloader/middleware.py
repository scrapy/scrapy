"""
Downloader Middleware manager

See documentation in docs/topics/downloader-middleware.rst
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, cast

from twisted.internet.defer import Deferred, inlineCallbacks

from scrapy.exceptions import ScrapyDeprecationWarning, _InvalidOutput
from scrapy.http import Request, Response
from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import _defer_sleep, deferred_from_coro
from scrapy.utils.deprecate import argument_is_required

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

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

    @inlineCallbacks
    def download(
        self,
        download_func: Callable[[Request], Deferred[Response]],
        request: Request,
        spider: Spider | None = None,
    ) -> Generator[Deferred[Any], Any, Response | Request]:
        if argument_is_required(download_func, "spider"):
            warnings.warn(
                "The spider argument of download_func is deprecated"
                " and will not be passed in future Scrapy versions.",
                ScrapyDeprecationWarning,
                stacklevel=2,
            )
            need_spider_arg = True
        else:
            need_spider_arg = False

        @inlineCallbacks
        def process_request(
            request: Request,
        ) -> Generator[Deferred[Any], Any, Response | Request]:
            for method in self.methods["process_request"]:
                method = cast("Callable", method)
                if method in self._mw_methods_requiring_spider:
                    response = yield deferred_from_coro(
                        method(request=request, spider=self._spider)
                    )
                else:
                    response = yield deferred_from_coro(method(request=request))
                if response is not None and not isinstance(
                    response, (Response, Request)
                ):
                    raise _InvalidOutput(
                        f"Middleware {method.__qualname__} must return None, Response or "
                        f"Request, got {response.__class__.__name__}"
                    )
                if response:
                    return response
            if need_spider_arg:
                return (yield download_func(request, self._spider))  # type: ignore[call-arg]
            return (yield download_func(request))

        @inlineCallbacks
        def process_response(
            response: Response | Request,
        ) -> Generator[Deferred[Any], Any, Response | Request]:
            if response is None:
                raise TypeError("Received None in process_response")
            if isinstance(response, Request):
                return response

            for method in self.methods["process_response"]:
                method = cast("Callable", method)
                if method in self._mw_methods_requiring_spider:
                    response = yield deferred_from_coro(
                        method(request=request, response=response, spider=self._spider)
                    )
                else:
                    response = yield deferred_from_coro(
                        method(request=request, response=response)
                    )
                if not isinstance(response, (Response, Request)):
                    raise _InvalidOutput(
                        f"Middleware {method.__qualname__} must return Response or Request, "
                        f"got {type(response)}"
                    )
                if isinstance(response, Request):
                    return response
            return response

        @inlineCallbacks
        def process_exception(
            exception: Exception,
        ) -> Generator[Deferred[Any], Any, Response | Request]:
            for method in self.methods["process_exception"]:
                method = cast("Callable", method)
                if method in self._mw_methods_requiring_spider:
                    response = yield deferred_from_coro(
                        method(
                            request=request, exception=exception, spider=self._spider
                        )
                    )
                else:
                    response = yield deferred_from_coro(
                        method(request=request, exception=exception)
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

        if spider:
            self._warn_spider_arg("download")
            self._set_compat_spider(spider)
        try:
            result: Response | Request = yield process_request(request)
        except Exception as ex:
            yield _defer_sleep()
            # either returns a request or response (which we pass to process_response())
            # or reraises the exception
            result = yield process_exception(ex)
        return (yield process_response(result))
