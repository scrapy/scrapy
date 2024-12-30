"""
Spider Middleware manager

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterable, Callable, Iterable
from inspect import isasyncgenfunction, iscoroutine
from itertools import islice
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.python.failure import Failure

from scrapy import Request, Spider
from scrapy.exceptions import _InvalidOutput
from scrapy.http import Response
from scrapy.middleware import MiddlewareManager
from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import (
    deferred_f_from_coro_f,
    deferred_from_coro,
    maybe_deferred_to_future,
    mustbe_deferred,
)
from scrapy.utils.python import MutableAsyncChain, MutableChain

if TYPE_CHECKING:
    from collections.abc import Generator

    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


_T = TypeVar("_T")
ScrapeFunc = Callable[
    [Union[Response, Failure], Request, Spider], Union[Iterable[_T], AsyncIterable[_T]]
]


def _isiterable(o: Any) -> bool:
    return isinstance(o, (Iterable, AsyncIterable))


class SpiderMiddlewareManager(MiddlewareManager):
    component_name = "spider middleware"

    def __init__(self, *middlewares: Any):
        super().__init__(*middlewares)
        self.downgrade_warning_done = False

    @classmethod
    def _get_mwlist_from_settings(cls, settings: BaseSettings) -> list[Any]:
        return build_component_list(settings.getwithbase("SPIDER_MIDDLEWARES"))

    def _add_middleware(self, mw: Any) -> None:
        super()._add_middleware(mw)
        if hasattr(mw, "process_spider_input"):
            self.methods["process_spider_input"].append(mw.process_spider_input)
        if hasattr(mw, "process_start_requests"):
            self.methods["process_start_requests"].appendleft(mw.process_start_requests)
        process_spider_output = self._get_async_method_pair(mw, "process_spider_output")
        self.methods["process_spider_output"].appendleft(process_spider_output)
        process_spider_exception = getattr(mw, "process_spider_exception", None)
        self.methods["process_spider_exception"].appendleft(process_spider_exception)

    def _process_spider_input(
        self,
        scrape_func: ScrapeFunc[_T],
        response: Response,
        request: Request,
        spider: Spider,
    ) -> Iterable[_T] | AsyncIterable[_T]:
        for method in self.methods["process_spider_input"]:
            method = cast(Callable, method)
            try:
                result = method(response=response, spider=spider)
                if result is not None:
                    msg = (
                        f"{method.__qualname__} must return None "
                        f"or raise an exception, got {type(result)}"
                    )
                    raise _InvalidOutput(msg)
            except _InvalidOutput:
                raise
            except Exception:
                return scrape_func(Failure(), request, spider)
        return scrape_func(response, request, spider)

    def _evaluate_iterable(
        self,
        response: Response,
        spider: Spider,
        iterable: Iterable[_T] | AsyncIterable[_T],
        exception_processor_index: int,
        recover_to: MutableChain[_T] | MutableAsyncChain[_T],
    ) -> Iterable[_T] | AsyncIterable[_T]:
        def process_sync(iterable: Iterable[_T]) -> Iterable[_T]:
            try:
                yield from iterable
            except Exception as ex:
                exception_result = cast(
                    Union[Failure, MutableChain[_T]],
                    self._process_spider_exception(
                        response, spider, Failure(ex), exception_processor_index
                    ),
                )
                if isinstance(exception_result, Failure):
                    raise
                assert isinstance(recover_to, MutableChain)
                recover_to.extend(exception_result)

        async def process_async(iterable: AsyncIterable[_T]) -> AsyncIterable[_T]:
            try:
                async for r in iterable:
                    yield r
            except Exception as ex:
                exception_result = cast(
                    Union[Failure, MutableAsyncChain[_T]],
                    self._process_spider_exception(
                        response, spider, Failure(ex), exception_processor_index
                    ),
                )
                if isinstance(exception_result, Failure):
                    raise
                assert isinstance(recover_to, MutableAsyncChain)
                recover_to.extend(exception_result)

        if isinstance(iterable, AsyncIterable):
            return process_async(iterable)
        return process_sync(iterable)

    def _process_spider_exception(
        self,
        response: Response,
        spider: Spider,
        _failure: Failure,
        start_index: int = 0,
    ) -> Failure | MutableChain[_T] | MutableAsyncChain[_T]:
        exception = _failure.value
        # don't handle _InvalidOutput exception
        if isinstance(exception, _InvalidOutput):
            return _failure
        method_list = islice(
            self.methods["process_spider_exception"], start_index, None
        )
        for method_index, method in enumerate(method_list, start=start_index):
            if method is None:
                continue
            method = cast(Callable, method)
            result = method(response=response, exception=exception, spider=spider)
            if _isiterable(result):
                # stop exception handling by handing control over to the
                # process_spider_output chain if an iterable has been returned
                dfd: Deferred[MutableChain[_T] | MutableAsyncChain[_T]] = (
                    self._process_spider_output(
                        response, spider, result, method_index + 1
                    )
                )
                # _process_spider_output() returns a Deferred only because of downgrading so this can be
                # simplified when downgrading is removed.
                if dfd.called:
                    # the result is available immediately if _process_spider_output didn't do downgrading
                    return cast(
                        Union[MutableChain[_T], MutableAsyncChain[_T]], dfd.result
                    )
                # we forbid waiting here because otherwise we would need to return a deferred from
                # _process_spider_exception too, which complicates the architecture
                msg = f"Async iterable returned from {method.__qualname__} cannot be downgraded"
                raise _InvalidOutput(msg)
            if result is None:
                continue
            msg = (
                f"{method.__qualname__} must return None "
                f"or an iterable, got {type(result)}"
            )
            raise _InvalidOutput(msg)
        return _failure

    # This method cannot be made async def, as _process_spider_exception relies on the Deferred result
    # being available immediately which doesn't work when it's a wrapped coroutine.
    # It also needs @inlineCallbacks only because of downgrading so it can be removed when downgrading is removed.
    @inlineCallbacks
    def _process_spider_output(
        self,
        response: Response,
        spider: Spider,
        result: Iterable[_T] | AsyncIterable[_T],
        start_index: int = 0,
    ) -> Generator[Deferred[Any], Any, MutableChain[_T] | MutableAsyncChain[_T]]:
        # items in this iterable do not need to go through the process_spider_output
        # chain, they went through it already from the process_spider_exception method
        recovered: MutableChain[_T] | MutableAsyncChain[_T]
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

        method_list = islice(self.methods["process_spider_output"], start_index, None)
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
                        logger.warning(
                            f"Async iterable passed to {method.__qualname__} "
                            f"was downgraded to a non-async one"
                        )
                        self.downgrade_warning_done = True
                    assert isinstance(result, AsyncIterable)
                    # AsyncIterable -> Iterable
                    result = yield deferred_from_coro(collect_asyncgen(result))
                    if isinstance(recovered, AsyncIterable):
                        recovered_collected = yield deferred_from_coro(
                            collect_asyncgen(recovered)
                        )
                        recovered = MutableChain(recovered_collected)
                # might fail directly if the output value is not a generator
                result = method(response=response, result=result, spider=spider)
            except Exception as ex:
                exception_result: Failure | MutableChain[_T] | MutableAsyncChain[_T] = (
                    self._process_spider_exception(
                        response, spider, Failure(ex), method_index + 1
                    )
                )
                if isinstance(exception_result, Failure):
                    raise
                return exception_result
            if _isiterable(result):
                result = self._evaluate_iterable(
                    response, spider, result, method_index + 1, recovered
                )
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
        return MutableChain(result, recovered)  # type: ignore[arg-type]

    async def _process_callback_output(
        self,
        response: Response,
        spider: Spider,
        result: Iterable[_T] | AsyncIterable[_T],
    ) -> MutableChain[_T] | MutableAsyncChain[_T]:
        recovered: MutableChain[_T] | MutableAsyncChain[_T]
        if isinstance(result, AsyncIterable):
            recovered = MutableAsyncChain()
        else:
            recovered = MutableChain()
        result = self._evaluate_iterable(response, spider, result, 0, recovered)
        result = await maybe_deferred_to_future(
            cast(
                "Deferred[Iterable[_T] | AsyncIterable[_T]]",
                self._process_spider_output(response, spider, result),
            )
        )
        if isinstance(result, AsyncIterable):
            return MutableAsyncChain(result, recovered)
        if isinstance(recovered, AsyncIterable):
            recovered_collected = await collect_asyncgen(recovered)
            recovered = MutableChain(recovered_collected)
        return MutableChain(result, recovered)

    def scrape_response(
        self,
        scrape_func: ScrapeFunc[_T],
        response: Response,
        request: Request,
        spider: Spider,
    ) -> Deferred[MutableChain[_T] | MutableAsyncChain[_T]]:
        async def process_callback_output(
            result: Iterable[_T] | AsyncIterable[_T],
        ) -> MutableChain[_T] | MutableAsyncChain[_T]:
            return await self._process_callback_output(response, spider, result)

        def process_spider_exception(
            _failure: Failure,
        ) -> Failure | MutableChain[_T] | MutableAsyncChain[_T]:
            return self._process_spider_exception(response, spider, _failure)

        dfd: Deferred[Iterable[_T] | AsyncIterable[_T]] = mustbe_deferred(
            self._process_spider_input, scrape_func, response, request, spider
        )
        dfd2: Deferred[MutableChain[_T] | MutableAsyncChain[_T]] = dfd.addCallback(
            deferred_f_from_coro_f(process_callback_output)
        )
        dfd2.addErrback(process_spider_exception)
        return dfd2

    def process_start_requests(
        self, start_requests: Iterable[Request], spider: Spider
    ) -> Deferred[Iterable[Request]]:
        return self._process_chain("process_start_requests", start_requests, spider)

    # This method is only needed until _async compatibility methods are removed.
    @staticmethod
    def _get_async_method_pair(
        mw: Any, methodname: str
    ) -> Callable | tuple[Callable, Callable] | None:
        normal_method: Callable | None = getattr(mw, methodname, None)
        methodname_async = methodname + "_async"
        async_method: Callable | None = getattr(mw, methodname_async, None)
        if not async_method:
            return normal_method
        if not normal_method:
            logger.error(
                f"Middleware {mw.__qualname__} has {methodname_async} "
                f"without {methodname}, skipping this method."
            )
            return None
        if not isasyncgenfunction(async_method):
            logger.error(
                f"{async_method.__qualname__} is not "
                f"an async generator function, skipping this method."
            )
            return normal_method
        if isasyncgenfunction(normal_method):
            logger.error(
                f"{normal_method.__qualname__} is an async "
                f"generator function while {methodname_async} exists, "
                f"skipping both methods."
            )
            return None
        return normal_method, async_method
