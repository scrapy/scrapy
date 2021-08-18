"""
Downloader Middleware manager

See documentation in docs/topics/downloader-middleware.rst
"""
from typing import Callable, Union

from twisted.internet import defer
from twisted.python.failure import Failure

from scrapy import Spider
from scrapy.exceptions import _InvalidOutput
from scrapy.http import Request, Response
from scrapy.middleware import MiddlewareManager
from scrapy.utils.defer import mustbe_deferred, deferred_from_coro
from scrapy.utils.conf import build_component_list


class DownloaderMiddlewareManager(MiddlewareManager):

    component_name = 'downloader middleware'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return build_component_list(
            settings.getwithbase('DOWNLOADER_MIDDLEWARES'))

    def _add_middleware(self, mw):
        if hasattr(mw, 'process_request'):
            self.methods['process_request'].append(mw.process_request)
        if hasattr(mw, 'process_response'):
            self.methods['process_response'].appendleft(mw.process_response)
        if hasattr(mw, 'process_exception'):
            self.methods['process_exception'].appendleft(mw.process_exception)

    def download(self, download_func: Callable, request: Request, spider: Spider):
        @defer.inlineCallbacks
        def process_request(request: Request):
            for method in self.methods['process_request']:
                response = yield deferred_from_coro(method(request=request, spider=spider))
                if response is not None and not isinstance(response, (Response, Request)):
                    raise _InvalidOutput(
                        f"Middleware {method.__qualname__} must return None, Response or "
                        f"Request, got {response.__class__.__name__}"
                    )
                if response:
                    return response
            return (yield download_func(request=request, spider=spider))

        @defer.inlineCallbacks
        def process_response(response: Union[Response, Request]):
            if response is None:
                raise TypeError("Received None in process_response")
            elif isinstance(response, Request):
                return response

            for method in self.methods['process_response']:
                response = yield deferred_from_coro(method(request=request, response=response, spider=spider))
                if not isinstance(response, (Response, Request)):
                    raise _InvalidOutput(
                        f"Middleware {method.__qualname__} must return Response or Request, "
                        f"got {type(response)}"
                    )
                if isinstance(response, Request):
                    return response
            return response

        @defer.inlineCallbacks
        def process_exception(failure: Failure):
            exception = failure.value
            for method in self.methods['process_exception']:
                response = yield deferred_from_coro(method(request=request, exception=exception, spider=spider))
                if response is not None and not isinstance(response, (Response, Request)):
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
