import logging
import warnings
import inspect
import asyncio

from functools import partial
from types import GeneratorType
from types import AsyncGeneratorType

from twisted.internet.defer import Deferred

from scrapy.http import Request
from scrapy.utils.spider import iterate_spider_output


logger = logging.getLogger(__name__)


class RequestGenerator(object):
    """This is the core class that wraps the callback and outputs the requests
    one by one.
    """

    def __init__(self, callback,crawler,spider, **kwargs):
        """Initialize RequestGenerator.

        Parameters
        ----------
        callback : callable
            Callable callback (spider method).
        **kwargs :
            Extra callback keyword arguments.

        """
        self.callback = callback
        self.kwargs = kwargs
        self.spider = spider
        self.crawler = crawler

    def __call__(self, response):
        """Main response entry point.

        This method calls the callback and wraps the returned generator.

        """
        method = self.callback(response=response, **self.kwargs)
        if isinstance(method, GeneratorType):
            output = iterate_spider_output(method)
        else :
            output = method

        if isinstance(output, AsyncGeneratorType):
            return (self._asyncunwindGenerator(output))
        if inspect.iscoroutine(output):
            return(self._asyncunwindGenerator(output))
        else:
            return self._unwindGenerator(output)

    
    async def _asyncunwindGenerator(self, asyncgen, _prev=None):
        if inspect.iscoroutine(asyncgen):
            asyncgen = await asyncgen
        while True:
            if _prev:
                ret, _prev = _prev, None
            else:
                try:
                    ret = await asyncgen.asend(None)
                except StopIteration as e:
                    ret = e.value
                except StopAsyncIteration:
                    break
                except TypeError:
                    break
                except AttributeError:
                    break
                
            if isinstance(ret, Request):
                if ret.callback:
                    pass
                elif ret.errback:
                    pass
                    # By Scrapy defaults, a request without callback defaults to
                    # self.parse spider method.
                else:
                    yield self._wrapRequest(ret, asyncgen)
                    return
            # A request with callbacks, item or None object.
            yield ret

    def _unwindGenerator(self, generator, _prev=None):
        """Unwind (resume) generator."""
        while True:
            if _prev:
                ret, _prev = _prev, None
            else:
                try:
                    ret = next(generator)
                except StopIteration:
                    break
                except TypeError:
                    break

            if isinstance(ret, Request):
                if ret.callback:
                    pass
                elif ret.errback:
                    pass
                    # By Scrapy defaults, a request without callback defaults to
                    # self.parse spider method.
                else:
                    yield self._wrapRequest(ret, generator)
                    return

            # A request with callbacks, item or None object.
            yield ret

    def _wrapRequest(self, request, generator):
        # Allowing existing callback or errbacks could lead to undesired
        # results. To ensure the generator is **always** properly exhausted we
        # must handle both callback and errback in order to send back the
        # result to the generator.
        if request.callback is not None:
            raise ValueError("Request with existing callback is not supported")
        if request.errback is not None:
            raise ValueError("Request with existing errback is not supported")

        request.callback = partial(self._handleSuccess, generator=generator)
        request.errback = partial(self._handleFailure, generator=generator)
        
        if isinstance(generator, AsyncGeneratorType):
            request.callback = partial(self._asynchandleSuccess, generator=generator)
        return request

    def _cleanRequest(self, request):
        request.callback = None
        request.errback = None

    def _handleSuccess(self, response, generator):
        if response.request:
            self._cleanRequest(response.request)
        try:
            ret = generator.send(response)
        except StopIteration:
            return
        return self._unwindGenerator(generator, ret)

    async def _asynchandleSuccess(self, response, generator):
        if response.request:
            self._cleanRequest(response.request)
        try:
            if generator is not None:
                ret = await generator.asend(response)
            else:
                ret = None
        except StopAsyncIteration as e:
            return
        return self._asyncunwindGenerator(generator,ret)
        

    def _handleFailure(self, failure, generator):
        # Look for the request instance in the exception value.
        if hasattr(failure.value, 'request'):
            self._cleanRequest(failure.value.request)
        elif hasattr(failure.value, 'response'):
            if hasattr(failure.value.response, 'request'):
                self._cleanRequest(failure.value.response.request)
        try:
            ret = failure.throwExceptionIntoGenerator(generator)
        except StopIteration:
            return
        return self._unwindGenerator(generator, ret)
