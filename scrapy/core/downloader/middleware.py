"""
Downloader Middleware manager

See documentation in docs/topics/downloader-middleware.rst
"""
from typing import Any, Callable, Generator, List, Union, cast

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.python.failure import Failure

from scrapy import Spider
from scrapy.exceptions import _InvalidOutput
from scrapy.http import Request, Response
from scrapy.middleware import MiddlewareManager
from scrapy.settings import BaseSettings
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import deferred_from_coro, mustbe_deferred


class DownloaderMiddlewareManager(MiddlewareManager):
    component_name = "downloader middleware"

    @classmethod
    def _get_mwlist_from_settings(cls, settings: BaseSettings) -> List[Any]:
        return build_component_list(settings.getwithbase("DOWNLOADER_MIDDLEWARES"))

    def _add_middleware(self, mw: Any) -> None:
        if hasattr(mw, "process_request"):
            self.methods["process_request"].append(mw.process_request)
        if hasattr(mw, "process_response"):
            self.methods["process_response"].appendleft(mw.process_response)
        if hasattr(mw, "process_exception"):
            self.methods["process_exception"].appendleft(mw.process_exception)

    def download(
        self, download_func: Callable, request: Request, spider: Spider
    ) -> Deferred:
        @inlineCallbacks
        def process_request(request: Request) -> Generator[Deferred, Any, Any]:
            for method in self.methods["process_request"]:
                method = cast(Callable, method)
                response = yield deferred_from_coro(
                    method(request=request, spider=spider)
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
            return (yield download_func(request=request, spider=spider))

        @inlineCallbacks
        def process_response(
            response: Union[Response, Request]
        ) -> Generator[Deferred, Any, Union[Response, Request]]:
            if response is None:
                raise TypeError("Received None in process_response")
            elif isinstance(response, Request):
                return response

            for method in self.methods["process_response"]:
                method = cast(Callable, method)
                response = yield deferred_from_coro(
                    method(request=request, response=response, spider=spider)
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
            failure: Failure,
        ) -> Generator[Deferred, Any, Union[Failure, Response, Request]]:
            exception = failure.value
            for method in self.methods["process_exception"]:
                method = cast(Callable, method)
                response = yield deferred_from_coro(
                    method(request=request, exception=exception, spider=spider)
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
            return failure

        deferred = mustbe_deferred(process_request, request)
        deferred.addErrback(process_exception)
        deferred.addCallback(process_response)
        return deferred
