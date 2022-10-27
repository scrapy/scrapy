"""
Spider Middleware manager

See documentation in docs/topics/spider-middleware.rst
"""
import logging
from inspect import isasyncgenfunction, iscoroutine
from itertools import islice
from typing import Any, AsyncGenerator, AsyncIterable, Callable, Generator, Iterable, Tuple, Union, cast

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.python.failure import Failure

from scrapy import Request, Spider
from scrapy.exceptions import _InvalidOutput
from scrapy.http import Response
from scrapy.middleware import MiddlewareManager
from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import mustbe_deferred, deferred_from_coro, deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.python import MutableAsyncChain, MutableChain


logger = logging.getLogger(__name__)


ScrapeFunc = Callable[[Union[Response, Failure], Request, Spider], Any]


def _isiterable(o) -> bool:
    return isinstance(o, (Iterable, AsyncIterable))


class SpiderMiddlewareManager(MiddlewareManager):

    component_name = 'spider middleware'

    def __init__(self, *middlewares):
        super().__init__(*middlewares)
        self.downgrade_warning_done = False

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return build_component_list(settings.getwithbase('SPIDER_MIDDLEWARES'))

    def _add_middleware(self, mw):
        super()._add_middleware(mw)
        if hasattr(mw, 'process_spider_input'):
            self.methods['process_spider_input'].append(mw.process_spider_input)
        if hasattr(mw, 'process_start_requests'):
            self.methods['process_start_requests'].appendleft(mw.process_start_requests)
        process_spider_output = self._get_async_method_pair(mw, 'process_spider_output')
        self.methods['process_spider_output'].appendleft(process_spider_output)
        process_spider_exception = getattr(mw, 'process_spider_exception', None)
        self.methods['process_spider_exception'].appendleft(process_spider_exception)

    def _process_spider_input(self, scrape_func: ScrapeFunc, response: Response, request: Request,
                              spider: Spider) -> Any:
        for method in self.methods['process_spider_input']:
            method = cast(Callable, method)
            try:
                result = method(response=response, spider=spider)
                if result is not None:
                    msg = (f"{method.__qualname__} must return None "
                           f"or raise an exception, got {type(result)}")
                    raise _InvalidOutput(msg)
            except _InvalidOutput:
                raise
            except Exception:
                return scrape_func(Failure(), request, spider)
        return scrape_func(response, request, spider)

    def _evaluate_iterable(self, response: Response, spider: Spider, iterable: Union[Iterable, AsyncIterable],
                           exception_processor_index: int, recover_to: Union[MutableChain, MutableAsyncChain]
                           ) -> Union[Generator, AsyncGenerator]:

        def process_sync(iterable: Iterable):
            try:
                for r in iterable:
                    yield r
            except Exception as ex:
                exception_result = self._process_spider_exception(response, spider, Failure(ex),
                                                                  exception_processor_index)
                if isinstance(exception_result, Failure):
                    raise
                recover_to.extend(exception_result)

        async def process_async(iterable: AsyncIterable):
            try:
                async for r in iterable:
                    yield r
            except Exception as ex:
                exception_result = self._process_spider_exception(response, spider, Failure(ex),
                                                                  exception_processor_index)
                if isinstance(exception_result, Failure):
                    raise
                recover_to.extend(exception_result)

        if isinstance(iterable, AsyncIterable):
            return process_async(iterable)
        return process_sync(iterable)

    def _process_spider_exception(self, response: Response, spider: Spider, _failure: Failure,
                                  start_index: int = 0) -> Union[Failure, MutableChain]:
        exception = _failure.value
        # don't handle _InvalidOutput exception
        if isinstance(exception, _InvalidOutput):
            return _failure
        method_list = islice(self.methods['process_spider_exception'], start_index, None)
        for method_index, method in enumerate(method_list, start=start_index):
            if method is None:
                continue
            method = cast(Callable, method)
            result = method(response=response, exception=exception, spider=spider)
            if _isiterable(result):
                # stop exception handling by handing control over to the
                # process_spider_output chain if an iterable has been returned
                dfd: Deferred = self._process_spider_output(response, spider, result, method_index + 1)
                # _process_spider_output() returns a Deferred only because of downgrading so this can be
                # simplified when downgrading is removed.
                if dfd.called:
                    # the result is available immediately if _process_spider_output didn't do downgrading
                    return dfd.result
                else:
                    # we forbid waiting here because otherwise we would need to return a deferred from
                    # _process_spider_exception too, which complicates the architecture
                    msg = f"Async iterable returned from {method.__qualname__} cannot be downgraded"
                    raise _InvalidOutput(msg)
            elif result is None:
                continue
            else:
                msg = (f"{method.__qualname__} must return None "
                       f"or an iterable, got {type(result)}")
                raise _InvalidOutput(msg)
        return _failure

    # This method cannot be made async def, as _process_spider_exception relies on the Deferred result
    # being available immediately which doesn't work when it's a wrapped coroutine.
    # It also needs @inlineCallbacks only because of downgrading so it can be removed when downgrading is removed.
    @inlineCallbacks
    def _process_spider_output(self, response: Response, spider: Spider,
                               result: Union[Iterable, AsyncIterable], start_index: int = 0
                               ) -> Deferred:
        # items in this iterable do not need to go through the process_spider_output
        # chain, they went through it already from the process_spider_exception method
        recovered: Union[MutableChain, MutableAsyncChain]
        last_result_is_async = isinstance(result, AsyncIterable)
        if last_result_is_async:
            recovered = MutableAsyncChain()
        else:
            recovered = MutableChain()

        # There are three cases for the middleware: def foo, async def foo, def foo + async def foo_async.
        # 1. def foo. Sync iterables are passed as is, async ones are downgraded.
        # 2. async def foo. Sync iterables are upgraded, async ones are passed as is.
        # 3. def foo + async def foo_async. Iterables are passed to the respective method.
        # Storing methods and method tuples in the same list is weird but we should be able to roll this back
        # when we drop this compatibility feature.

        method_list = islice(self.methods['process_spider_output'], start_index, None)
        for method_index, method_pair in enumerate(method_list, start=start_index):
            if method_pair is None:
                continue
            need_upgrade = need_downgrade = False
            if isinstance(method_pair, tuple):
                # This tuple handling is only needed until _async compatibility methods are removed.
                method_sync, method_async = method_pair
                method = method_async if last_result_is_async else method_sync
            else:
                method = method_pair
                if not last_result_is_async and isasyncgenfunction(method):
                    need_upgrade = True
                elif last_result_is_async and not isasyncgenfunction(method):
                    need_downgrade = True
            try:
                if need_upgrade:
                    # Iterable -> AsyncIterable
                    result = as_async_generator(result)
                elif need_downgrade:
                    if not self.downgrade_warning_done:
                        logger.warning(f"Async iterable passed to {method.__qualname__} "
                                       f"was downgraded to a non-async one")
                        self.downgrade_warning_done = True
                    assert isinstance(result, AsyncIterable)
                    # AsyncIterable -> Iterable
                    result = yield deferred_from_coro(collect_asyncgen(result))
                    if isinstance(recovered, AsyncIterable):
                        recovered_collected = yield deferred_from_coro(collect_asyncgen(recovered))
                        recovered = MutableChain(recovered_collected)
                # might fail directly if the output value is not a generator
                result = method(response=response, result=result, spider=spider)
            except Exception as ex:
                exception_result = self._process_spider_exception(response, spider, Failure(ex), method_index + 1)
                if isinstance(exception_result, Failure):
                    raise
                return exception_result
            if _isiterable(result):
                result = self._evaluate_iterable(response, spider, result, method_index + 1, recovered)
            else:
                if iscoroutine(result):
                    result.close()  # Silence warning about not awaiting
                    msg = (
                        f"{method.__qualname__} must be an asynchronous "
                        f"generator (i.e. use yield)"
                    )
                else:
                    msg = (
                        f"{method.__qualname__} must return an iterable, got "
                        f"{type(result)}"
                    )
                raise _InvalidOutput(msg)
            last_result_is_async = isinstance(result, AsyncIterable)

        if last_result_is_async:
            return MutableAsyncChain(result, recovered)
        else:
            return MutableChain(result, recovered)  # type: ignore[arg-type]

    async def _process_callback_output(self, response: Response, spider: Spider, result: Union[Iterable, AsyncIterable]
                                       ) -> Union[MutableChain, MutableAsyncChain]:
        recovered: Union[MutableChain, MutableAsyncChain]
        if isinstance(result, AsyncIterable):
            recovered = MutableAsyncChain()
        else:
            recovered = MutableChain()
        result = self._evaluate_iterable(response, spider, result, 0, recovered)
        result = await maybe_deferred_to_future(self._process_spider_output(response, spider, result))
        if isinstance(result, AsyncIterable):
            return MutableAsyncChain(result, recovered)
        else:
            if isinstance(recovered, AsyncIterable):
                recovered_collected = await collect_asyncgen(recovered)
                recovered = MutableChain(recovered_collected)
            return MutableChain(result, recovered)  # type: ignore[arg-type]

    def scrape_response(self, scrape_func: ScrapeFunc, response: Response, request: Request,
                        spider: Spider) -> Deferred:
        async def process_callback_output(result: Union[Iterable, AsyncIterable]
                                          ) -> Union[MutableChain, MutableAsyncChain]:
            return await self._process_callback_output(response, spider, result)

        def process_spider_exception(_failure: Failure) -> Union[Failure, MutableChain]:
            return self._process_spider_exception(response, spider, _failure)

        dfd = mustbe_deferred(self._process_spider_input, scrape_func, response, request, spider)
        dfd.addCallbacks(callback=deferred_f_from_coro_f(process_callback_output), errback=process_spider_exception)
        return dfd

    def process_start_requests(self, start_requests, spider: Spider) -> Deferred:
        return self._process_chain('process_start_requests', start_requests, spider)

    # This method is only needed until _async compatibility methods are removed.
    @staticmethod
    def _get_async_method_pair(mw: Any, methodname: str) -> Union[None, Callable, Tuple[Callable, Callable]]:
        normal_method = getattr(mw, methodname, None)
        methodname_async = methodname + "_async"
        async_method = getattr(mw, methodname_async, None)
        if not async_method:
            return normal_method
        if not normal_method:
            logger.error(f"Middleware {mw.__qualname__} has {methodname_async} "
                         f"without {methodname}, skipping this method.")
            return None
        if not isasyncgenfunction(async_method):
            logger.error(f"{async_method.__qualname__} is not "
                         f"an async generator function, skipping this method.")
            return normal_method
        if isasyncgenfunction(normal_method):
            logger.error(f"{normal_method.__qualname__} is an async "
                         f"generator function while {methodname_async} exists, "
                         f"skipping both methods.")
            return None
        return normal_method, async_method
