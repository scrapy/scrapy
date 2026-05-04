"""
Spider Middleware manager

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Coroutine, Iterable
from functools import wraps
from inspect import isasyncgenfunction, iscoroutine
from itertools import islice
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar, cast
from warnings import warn

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.python.failure import Failure

from scrapy import Request, Spider
from scrapy.exceptions import ScrapyDeprecationWarning, _InvalidOutput
from scrapy.http import Response
from scrapy.middleware import MiddlewareManager
from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import (
    _defer_sleep_async,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from scrapy.utils.python import MutableAsyncChain, MutableChain, global_object_name

if TYPE_CHECKING:
    from collections.abc import Generator

    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


_T = TypeVar("_T")
ScrapeFunc: TypeAlias = Callable[
    [Response | Failure, Request],
    Coroutine[Any, Any, Iterable[_T] | AsyncIterator[_T]],
]


def _isiterable(o: Any) -> bool:
    return isinstance(o, (Iterable, AsyncIterator))


class SpiderMiddlewareManager(MiddlewareManager):
    component_name = "spider middleware"

    @classmethod
    def _get_mwlist_from_settings(cls, settings: BaseSettings) -> list[Any]:
        return build_component_list(
            settings.get_component_priority_dict_with_base("SPIDER_MIDDLEWARES")
        )

    def _add_middleware(self, mw: Any) -> None:
        if hasattr(mw, "process_spider_input"):
            self.methods["process_spider_input"].append(mw.process_spider_input)
            self._check_mw_method_spider_arg(mw.process_spider_input)

        if hasattr(mw, "process_start"):
            self.methods["process_start"].appendleft(mw.process_start)

        process_spider_output = self._get_async_method_pair(mw, "process_spider_output")
        self.methods["process_spider_output"].appendleft(process_spider_output)
        if callable(process_spider_output):
            self._check_mw_method_spider_arg(process_spider_output)
        elif isinstance(process_spider_output, tuple):
            for m in process_spider_output:
                self._check_mw_method_spider_arg(m)

        process_spider_exception = getattr(mw, "process_spider_exception", None)
        self.methods["process_spider_exception"].appendleft(process_spider_exception)
        if process_spider_exception is not None:
            self._check_mw_method_spider_arg(process_spider_exception)

    async def _process_spider_input(
        self,
        scrape_func: ScrapeFunc[_T],
        response: Response,
        request: Request,
    ) -> Iterable[_T] | AsyncIterator[_T]:
        for method in self.methods["process_spider_input"]:
            method = cast("Callable", method)
            try:
                if method in self._mw_methods_requiring_spider:
                    result = method(response=response, spider=self._spider)
                else:
                    result = method(response=response)
                if result is not None:
                    msg = (
                        f"{global_object_name(method)} must return None "
                        f"or raise an exception, got {type(result)}"
                    )
                    raise _InvalidOutput(msg)
            except _InvalidOutput:
                raise
            except Exception:
                return await scrape_func(Failure(), request)
        return await scrape_func(response, request)

    def _evaluate_iterable(
        self,
        response: Response,
        iterable: Iterable[_T] | AsyncIterator[_T],
        exception_processor_index: int,
        recover_to: MutableChain[_T] | MutableAsyncChain[_T],
    ) -> Iterable[_T] | AsyncIterator[_T]:

        if isinstance(iterable, AsyncIterator):
            return self._process_async(
                response,
                iterable,
                exception_processor_index,
                cast("MutableAsyncChain[_T]", recover_to),
            )
        return self._process_sync(
            response,
            iterable,
            exception_processor_index,
            cast("MutableChain[_T]", recover_to),
        )

    def _process_sync(
        self,
        response: Response,
        iterable: Iterable[_T],
        exception_processor_index: int,
        recover_to: MutableChain[_T],
    ) -> Iterable[_T]:
        try:
            yield from iterable
        except Exception as ex:
            exception_result = cast(
                "Failure | MutableChain[_T]",
                self._process_spider_exception(response, ex, exception_processor_index),
            )
            if isinstance(exception_result, Failure):
                raise
            assert isinstance(recover_to, MutableChain)
            recover_to.extend(exception_result)

    async def _process_async(
        self,
        response: Response,
        iterable: AsyncIterator[_T],
        exception_processor_index: int,
        recover_to: MutableAsyncChain[_T],
    ) -> AsyncIterator[_T]:
        try:
            async for r in iterable:
                yield r
        except Exception as ex:
            exception_result = cast(
                "Failure | MutableAsyncChain[_T]",
                self._process_spider_exception(response, ex, exception_processor_index),
            )
            if isinstance(exception_result, Failure):
                raise
            assert isinstance(recover_to, MutableAsyncChain)
            recover_to.extend(exception_result)

    def _process_spider_exception(
        self,
        response: Response,
        exception: Exception,
        start_index: int = 0,
    ) -> MutableChain[_T] | MutableAsyncChain[_T]:
        # don't handle _InvalidOutput exception
        if isinstance(exception, _InvalidOutput):
            raise exception
        method_list = islice(
            self.methods["process_spider_exception"], start_index, None
        )
        for method_index, method in enumerate(method_list, start=start_index):
            if method is None:
                continue
            method = cast("Callable", method)
            if method in self._mw_methods_requiring_spider:
                result = method(
                    response=response, exception=exception, spider=self._spider
                )
            else:
                result = method(response=response, exception=exception)
            if _isiterable(result):
                # stop exception handling by handing control over to the
                # process_spider_output chain if an iterable has been returned
                dfd: Deferred[MutableChain[_T] | MutableAsyncChain[_T]] = (
                    self._process_spider_output(response, result, method_index + 1)
                )
                # _process_spider_output() returns a Deferred only because of downgrading so this can be
                # simplified when downgrading is removed.
                if dfd.called:
                    # the result is available immediately if _process_spider_output didn't do downgrading
                    return cast("MutableChain[_T] | MutableAsyncChain[_T]", dfd.result)
                # we forbid waiting here because otherwise we would need to return a deferred from
                # _process_spider_exception too, which complicates the architecture
                msg = f"Async iterable returned from {global_object_name(method)} cannot be downgraded"
                raise _InvalidOutput(msg)
            if result is None:
                continue
            msg = (
                f"{global_object_name(method)} must return None "
                f"or an iterable, got {type(result)}"
            )
            raise _InvalidOutput(msg)
        raise exception

    # This method cannot be made async def, as _process_spider_exception relies on the Deferred result
    # being available immediately which doesn't work when it's a wrapped coroutine.
    # It also needs @inlineCallbacks only because of downgrading so it can be removed when downgrading is removed.
    @inlineCallbacks
    def _process_spider_output(  # noqa: PLR0912
        self,
        response: Response,
        result: Iterable[_T] | AsyncIterator[_T],
        start_index: int = 0,
    ) -> Generator[Deferred[Any], Any, MutableChain[_T] | MutableAsyncChain[_T]]:
        # items in this iterable do not need to go through the process_spider_output
        # chain, they went through it already from the process_spider_exception method
        recovered: MutableChain[_T] | MutableAsyncChain[_T]
        last_result_is_async = isinstance(result, AsyncIterator)
        recovered = MutableAsyncChain() if last_result_is_async else MutableChain()

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
                    # Iterable -> AsyncIterator
                    result = as_async_generator(result)
                elif need_downgrade:
                    logger.warning(
                        f"Async iterable passed to {global_object_name(method)} was"
                        f" downgraded to a non-async one. This is deprecated and will"
                        f" stop working in a future version of Scrapy. Please see"
                        f" https://docs.scrapy.org/en/latest/topics/coroutines.html#for-middleware-users"
                        f" for more information."
                    )
                    assert isinstance(result, AsyncIterator)
                    # AsyncIterator -> Iterable
                    result = yield deferred_from_coro(collect_asyncgen(result))
                    if isinstance(recovered, AsyncIterator):
                        recovered_collected = yield deferred_from_coro(
                            collect_asyncgen(recovered)
                        )
                        recovered = MutableChain(recovered_collected)
                # might fail directly if the output value is not a generator
                if method in self._mw_methods_requiring_spider:
                    result = method(
                        response=response, result=result, spider=self._spider
                    )
                else:
                    result = method(response=response, result=result)
            except Exception as ex:
                exception_result: Failure | MutableChain[_T] | MutableAsyncChain[_T] = (
                    self._process_spider_exception(response, ex, method_index + 1)
                )
                if isinstance(exception_result, Failure):
                    raise
                return exception_result
            if _isiterable(result):
                result = self._evaluate_iterable(
                    response, result, method_index + 1, recovered
                )
            else:
                if iscoroutine(result):
                    result.close()  # Silence warning about not awaiting
                    msg = (
                        f"{global_object_name(method)} must be an asynchronous "
                        f"generator (i.e. use yield)"
                    )
                else:
                    msg = (
                        f"{global_object_name(method)} must return an iterable, got "
                        f"{type(result)}"
                    )
                raise _InvalidOutput(msg)
            last_result_is_async = isinstance(result, AsyncIterator)

        if last_result_is_async:
            return MutableAsyncChain(result, recovered)
        return MutableChain(result, recovered)  # type: ignore[arg-type]

    async def _process_callback_output(
        self,
        response: Response,
        result: Iterable[_T] | AsyncIterator[_T],
    ) -> MutableChain[_T] | MutableAsyncChain[_T]:
        recovered: MutableChain[_T] | MutableAsyncChain[_T]
        if isinstance(result, AsyncIterator):
            recovered = MutableAsyncChain()
        else:
            recovered = MutableChain()
        result = self._evaluate_iterable(response, result, 0, recovered)
        result = await maybe_deferred_to_future(
            cast(
                "Deferred[Iterable[_T] | AsyncIterator[_T]]",
                self._process_spider_output(response, result),
            )
        )
        if isinstance(result, AsyncIterator):
            return MutableAsyncChain(result, recovered)
        if isinstance(recovered, AsyncIterator):
            recovered_collected = await collect_asyncgen(recovered)
            recovered = MutableChain(recovered_collected)
        return MutableChain(result, recovered)

    def scrape_response(
        self,
        scrape_func: Callable[
            [Response | Failure, Request],
            Deferred[Iterable[_T] | AsyncIterator[_T]],
        ],
        response: Response,
        request: Request,
        spider: Spider,
    ) -> Deferred[MutableChain[_T] | MutableAsyncChain[_T]]:  # pragma: no cover
        warn(
            "SpiderMiddlewareManager.scrape_response() is deprecated, use scrape_response_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )

        @wraps(scrape_func)
        async def scrape_func_wrapped(
            response: Response | Failure, request: Request
        ) -> Iterable[_T] | AsyncIterator[_T]:
            return await maybe_deferred_to_future(scrape_func(response, request))

        self._set_compat_spider(spider)
        return deferred_from_coro(
            self.scrape_response_async(scrape_func_wrapped, response, request)
        )

    async def scrape_response_async(
        self,
        scrape_func: ScrapeFunc[_T],
        response: Response,
        request: Request,
    ) -> MutableChain[_T] | MutableAsyncChain[_T]:
        if not self.crawler:
            raise RuntimeError(
                "scrape_response_async() called on a SpiderMiddlewareManager"
                " instance created without a crawler."
            )
        try:
            it: Iterable[_T] | AsyncIterator[_T] = await self._process_spider_input(
                scrape_func, response, request
            )
            return await self._process_callback_output(response, it)
        except Exception as ex:
            await _defer_sleep_async()
            return self._process_spider_exception(response, ex)

    async def process_start(
        self, spider: Spider | None = None
    ) -> AsyncIterator[Any] | None:
        if spider:
            if self.crawler:
                msg = (
                    "Passing a spider argument to SpiderMiddlewareManager.process_start() is deprecated"
                    " and the passed value is ignored."
                )
            else:
                msg = (
                    "Passing a spider argument to SpiderMiddlewareManager.process_start() is deprecated,"
                    " SpiderMiddlewareManager should be instantiated with a Crawler instance instead."
                )
            warn(msg, category=ScrapyDeprecationWarning, stacklevel=2)
            self._set_compat_spider(spider)
        start = self._spider.start()
        return await self._process_chain("process_start", start)

    # This method is only needed until _async compatibility methods are removed.
    @staticmethod
    def _get_async_method_pair(
        mw: Any, methodname: str
    ) -> Callable | tuple[Callable, Callable] | None:
        normal_method: Callable | None = getattr(mw, methodname, None)
        methodname_async = methodname + "_async"
        async_method: Callable | None = getattr(mw, methodname_async, None)
        if not async_method:
            if normal_method and not isasyncgenfunction(normal_method):
                logger.warning(
                    f"Middleware {global_object_name(mw.__class__)} doesn't support"
                    f" asynchronous spider output, this is deprecated and will stop"
                    f" working in a future version of Scrapy. The middleware should"
                    f" be updated to support it. Please see"
                    f" https://docs.scrapy.org/en/latest/topics/coroutines.html#for-middleware-users"
                    f" for more information."
                )
            return normal_method
        if not normal_method:
            logger.error(
                f"Middleware {global_object_name(mw.__class__)} has {methodname_async} "
                f"without {methodname}, skipping this method."
            )
            return None
        if not isasyncgenfunction(async_method):
            logger.error(
                f"{global_object_name(async_method)} is not "
                f"an async generator function, skipping this method."
            )
            return normal_method
        if isasyncgenfunction(normal_method):
            logger.error(
                f"{global_object_name(normal_method)} is an async "
                f"generator function while {methodname_async} exists, "
                f"skipping both methods."
            )
            return None
        return normal_method, async_method
