"""
Spider Middleware manager

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Coroutine, Iterable
from functools import wraps
from inspect import isasyncgenfunction
from itertools import islice
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar, cast
from warnings import warn

from twisted.python.failure import Failure

from scrapy import Request, Spider
from scrapy.exceptions import ScrapyDeprecationWarning, _InvalidOutput
from scrapy.http import Response
from scrapy.middleware import MiddlewareManager
from scrapy.utils.asyncgen import as_async_generator
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import (
    _defer_sleep_async,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from scrapy.utils.python import MutableAsyncChain, global_object_name

if TYPE_CHECKING:
    from twisted.internet.defer import Deferred

    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


_T = TypeVar("_T")
ScrapeFunc: TypeAlias = Callable[
    [Response | Failure, Request],
    Coroutine[Any, Any, Iterable[_T] | AsyncIterator[_T]],
]


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

        process_spider_output = self._get_process_spider_output(mw)
        self.methods["process_spider_output"].appendleft(process_spider_output)
        if process_spider_output is not None:
            self._check_mw_method_spider_arg(process_spider_output)

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

    async def _evaluate_iterable(
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
            exception_result: MutableAsyncChain[_T] = self._process_spider_exception(
                response, ex, exception_processor_index
            )
            recover_to.extend(exception_result)

    def _process_spider_exception(
        self,
        response: Response,
        exception: Exception,
        start_index: int = 0,
    ) -> MutableAsyncChain[_T]:
        # don't handle _InvalidOutput exception
        if isinstance(exception, _InvalidOutput):
            raise exception
        method_list = islice(
            self.methods["process_spider_exception"], start_index, None
        )
        for method_index, method in enumerate(method_list, start=start_index):
            if method is None:
                continue
            if method in self._mw_methods_requiring_spider:
                result = method(
                    response=response, exception=exception, spider=self._spider
                )
            else:
                result = method(response=response, exception=exception)
            if isinstance(result, (Iterable, AsyncIterator)):
                # stop exception handling by handing control over to the
                # process_spider_output chain if an iterable has been returned
                if isinstance(result, Iterable):
                    result = as_async_generator(result)
                return self._process_spider_output(response, result, method_index + 1)
            if result is None:
                continue
            msg = (
                f"{global_object_name(method)} must return None "
                f"or an iterable, got {type(result)}"
            )
            raise _InvalidOutput(msg)
        raise exception

    def _process_spider_output(
        self,
        response: Response,
        result: AsyncIterator[_T],
        start_index: int = 0,
    ) -> MutableAsyncChain[_T]:
        # items in this iterable do not need to go through the process_spider_output
        # chain, they went through it already from the process_spider_exception method
        recovered: MutableAsyncChain[_T] = MutableAsyncChain()
        method_list = islice(self.methods["process_spider_output"], start_index, None)
        for method_index, method in enumerate(method_list, start=start_index):
            if method is None:
                continue
            if method in self._mw_methods_requiring_spider:
                result = method(response=response, result=result, spider=self._spider)
            else:
                result = method(response=response, result=result)
            result = self._evaluate_iterable(
                response, result, method_index + 1, recovered
            )
        return MutableAsyncChain(result, recovered)

    async def _process_callback_output(
        self, response: Response, result: AsyncIterator[_T]
    ) -> MutableAsyncChain[_T]:
        recovered: MutableAsyncChain[_T] = MutableAsyncChain()
        result = self._evaluate_iterable(response, result, 0, recovered)
        result = self._process_spider_output(response, result)
        return MutableAsyncChain(result, recovered)

    def scrape_response(
        self,
        scrape_func: Callable[
            [Response | Failure, Request],
            Deferred[Iterable[_T] | AsyncIterator[_T]],
        ],
        response: Response,
        request: Request,
        spider: Spider,
    ) -> Deferred[MutableAsyncChain[_T]]:  # pragma: no cover
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
    ) -> MutableAsyncChain[_T]:
        if not self.crawler:
            raise RuntimeError(
                "scrape_response_async() called on a SpiderMiddlewareManager"
                " instance created without a crawler."
            )
        try:
            it: Iterable[_T] | AsyncIterator[_T] = await self._process_spider_input(
                scrape_func, response, request
            )
            ait = it if isinstance(it, AsyncIterator) else as_async_generator(it)
            return await self._process_callback_output(response, ait)
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
    def _get_process_spider_output(mw: Any) -> Callable | None:
        normal_method: Callable | None = getattr(mw, "process_spider_output", None)
        async_method: Callable | None = getattr(mw, "process_spider_output_async", None)
        if not async_method:
            if normal_method and not isasyncgenfunction(normal_method):
                raise TypeError(
                    f"Middleware {global_object_name(mw.__class__)} doesn't support"
                    f" asynchronous spider output. Its process_spider_output() method"
                    f" should be an async generator function or it should additionally"
                    f" define a process_spider_output_async() method."
                )
            return normal_method
        if not normal_method:
            logger.error(
                f"Middleware {global_object_name(mw.__class__)} has"
                f" process_spider_output_async() without process_spider_output(),"
                f" skipping this method. Please rename it to process_spider_output()."
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
                f"generator function while process_spider_output_async() exists, "
                f"skipping both methods. Please remove process_spider_output_async()."
            )
            return None
        return async_method
