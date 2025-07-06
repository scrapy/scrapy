from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from inspect import isasyncgen
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from testfixtures import LogCapture
from twisted.internet import defer

from scrapy.core.spidermw import SpiderMiddlewareManager
from scrapy.exceptions import _InvalidOutput
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.utils.asyncgen import collect_asyncgen
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from twisted.python.failure import Failure


class TestSpiderMiddleware:
    def setup_method(self):
        self.request = Request("http://example.com/index.html")
        self.response = Response(self.request.url, request=self.request)
        self.crawler = get_crawler(Spider, {"SPIDER_MIDDLEWARES_BASE": {}})
        self.spider = self.crawler._create_spider("foo")
        self.mwman = SpiderMiddlewareManager.from_crawler(self.crawler)

    async def _scrape_response(self) -> Any:
        """Execute spider mw manager's scrape_response method and return the result.
        Raise exception in case of failure.
        """

        def scrape_func(
            response: Response | Failure, request: Request
        ) -> defer.Deferred[Iterable[Any]]:
            it = mock.MagicMock()
            return defer.succeed(it)

        return await maybe_deferred_to_future(
            self.mwman.scrape_response(
                scrape_func, self.response, self.request, self.spider
            )
        )


class TestProcessSpiderInputInvalidOutput(TestSpiderMiddleware):
    """Invalid return value for process_spider_input method"""

    @deferred_f_from_coro_f
    async def test_invalid_process_spider_input(self):
        class InvalidProcessSpiderInputMiddleware:
            def process_spider_input(self, response, spider):
                return 1

        self.mwman._add_middleware(InvalidProcessSpiderInputMiddleware())
        with pytest.raises(_InvalidOutput):
            await self._scrape_response()


class TestProcessSpiderOutputInvalidOutput(TestSpiderMiddleware):
    """Invalid return value for process_spider_output method"""

    @deferred_f_from_coro_f
    async def test_invalid_process_spider_output(self):
        class InvalidProcessSpiderOutputMiddleware:
            def process_spider_output(self, response, result, spider):
                return 1

        self.mwman._add_middleware(InvalidProcessSpiderOutputMiddleware())
        with pytest.raises(_InvalidOutput):
            await self._scrape_response()


class TestProcessSpiderExceptionInvalidOutput(TestSpiderMiddleware):
    """Invalid return value for process_spider_exception method"""

    @deferred_f_from_coro_f
    async def test_invalid_process_spider_exception(self):
        class InvalidProcessSpiderOutputExceptionMiddleware:
            def process_spider_exception(self, response, exception, spider):
                return 1

        class RaiseExceptionProcessSpiderOutputMiddleware:
            def process_spider_output(self, response, result, spider):
                raise RuntimeError

        self.mwman._add_middleware(InvalidProcessSpiderOutputExceptionMiddleware())
        self.mwman._add_middleware(RaiseExceptionProcessSpiderOutputMiddleware())
        with pytest.raises(_InvalidOutput):
            await self._scrape_response()


class TestProcessSpiderExceptionReRaise(TestSpiderMiddleware):
    """Re raise the exception by returning None"""

    @deferred_f_from_coro_f
    async def test_process_spider_exception_return_none(self):
        class ProcessSpiderExceptionReturnNoneMiddleware:
            def process_spider_exception(self, response, exception, spider):
                return None

        class RaiseExceptionProcessSpiderOutputMiddleware:
            def process_spider_output(self, response, result, spider):
                1 / 0

        self.mwman._add_middleware(ProcessSpiderExceptionReturnNoneMiddleware())
        self.mwman._add_middleware(RaiseExceptionProcessSpiderOutputMiddleware())
        with pytest.raises(ZeroDivisionError):
            await self._scrape_response()


class TestBaseAsyncSpiderMiddleware(TestSpiderMiddleware):
    """Helpers for testing sync, async and mixed middlewares.

    Should work for process_spider_output and, when it's supported, process_start.
    """

    ITEM_TYPE: type | tuple
    RESULT_COUNT = 3  # to simplify checks, let everything return 3 objects

    @staticmethod
    def _construct_mw_setting(
        *mw_classes: type[Any], start_index: int | None = None
    ) -> dict[type[Any], int]:
        if start_index is None:
            start_index = 10
        return {i: c for c, i in enumerate(mw_classes, start=start_index)}

    def _callback(self) -> Any:
        yield {"foo": 1}
        yield {"foo": 2}
        yield {"foo": 3}

    def _scrape_func(
        self, response: Response | Failure, request: Request
    ) -> defer.Deferred[Iterable[Any] | AsyncIterator[Any]]:
        return defer.succeed(self._callback())

    async def _get_middleware_result(
        self, *mw_classes: type[Any], start_index: int | None = None
    ) -> Any:
        setting = self._construct_mw_setting(*mw_classes, start_index=start_index)
        self.crawler = get_crawler(
            Spider, {"SPIDER_MIDDLEWARES_BASE": {}, "SPIDER_MIDDLEWARES": setting}
        )
        self.spider = self.crawler._create_spider("foo")
        self.mwman = SpiderMiddlewareManager.from_crawler(self.crawler)
        return await self.mwman.scrape_response_async(
            self._scrape_func, self.response, self.request, self.spider
        )

    async def _test_simple_base(
        self,
        *mw_classes: type[Any],
        downgrade: bool = False,
        start_index: int | None = None,
    ) -> None:
        with LogCapture() as log:
            result = await self._get_middleware_result(
                *mw_classes, start_index=start_index
            )
        assert isinstance(result, Iterable)
        result_list = list(result)
        assert len(result_list) == self.RESULT_COUNT
        assert isinstance(result_list[0], self.ITEM_TYPE)
        assert ("downgraded to a non-async" in str(log)) == downgrade
        assert ("doesn't support asynchronous spider output" in str(log)) == (
            ProcessSpiderOutputSimpleMiddleware in mw_classes
        )

    async def _test_asyncgen_base(
        self,
        *mw_classes: type[Any],
        downgrade: bool = False,
        start_index: int | None = None,
    ) -> None:
        with LogCapture() as log:
            result = await self._get_middleware_result(
                *mw_classes, start_index=start_index
            )
        assert isinstance(result, AsyncIterator)
        result_list = await collect_asyncgen(result)
        assert len(result_list) == self.RESULT_COUNT
        assert isinstance(result_list[0], self.ITEM_TYPE)
        assert ("downgraded to a non-async" in str(log)) == downgrade


class ProcessSpiderOutputSimpleMiddleware:
    def process_spider_output(self, response, result, spider):
        yield from result


class ProcessSpiderOutputAsyncGenMiddleware:
    async def process_spider_output(self, response, result, spider):
        async for r in result:
            yield r


class ProcessSpiderOutputUniversalMiddleware:
    def process_spider_output(self, response, result, spider):
        yield from result

    async def process_spider_output_async(self, response, result, spider):
        async for r in result:
            yield r


class ProcessSpiderExceptionSimpleIterableMiddleware:
    def process_spider_exception(self, response, exception, spider):
        yield {"foo": 1}
        yield {"foo": 2}
        yield {"foo": 3}


class ProcessSpiderExceptionAsyncIteratorMiddleware:
    async def process_spider_exception(self, response, exception, spider):
        yield {"foo": 1}
        d = defer.Deferred()
        from twisted.internet import reactor

        reactor.callLater(0, d.callback, None)
        await maybe_deferred_to_future(d)
        yield {"foo": 2}
        yield {"foo": 3}


class TestProcessSpiderOutputSimple(TestBaseAsyncSpiderMiddleware):
    """process_spider_output tests for simple callbacks"""

    ITEM_TYPE = dict
    MW_SIMPLE = ProcessSpiderOutputSimpleMiddleware
    MW_ASYNCGEN = ProcessSpiderOutputAsyncGenMiddleware
    MW_UNIVERSAL = ProcessSpiderOutputUniversalMiddleware

    @deferred_f_from_coro_f
    async def test_simple(self):
        """Simple mw"""
        await self._test_simple_base(self.MW_SIMPLE)

    @deferred_f_from_coro_f
    async def test_asyncgen(self):
        """Asyncgen mw; upgrade"""
        await self._test_asyncgen_base(self.MW_ASYNCGEN)

    @deferred_f_from_coro_f
    async def test_simple_asyncgen(self):
        """Simple mw -> asyncgen mw; upgrade"""
        await self._test_asyncgen_base(self.MW_ASYNCGEN, self.MW_SIMPLE)

    @deferred_f_from_coro_f
    async def test_asyncgen_simple(self):
        """Asyncgen mw -> simple mw; upgrade then downgrade"""
        await self._test_simple_base(self.MW_SIMPLE, self.MW_ASYNCGEN, downgrade=True)

    @deferred_f_from_coro_f
    async def test_universal(self):
        """Universal mw"""
        await self._test_simple_base(self.MW_UNIVERSAL)

    @deferred_f_from_coro_f
    async def test_universal_simple(self):
        """Universal mw -> simple mw"""
        await self._test_simple_base(self.MW_SIMPLE, self.MW_UNIVERSAL)

    @deferred_f_from_coro_f
    async def test_simple_universal(self):
        """Simple mw -> universal mw"""
        await self._test_simple_base(self.MW_UNIVERSAL, self.MW_SIMPLE)

    @deferred_f_from_coro_f
    async def test_universal_asyncgen(self):
        """Universal mw -> asyncgen mw; upgrade"""
        await self._test_asyncgen_base(self.MW_ASYNCGEN, self.MW_UNIVERSAL)

    @deferred_f_from_coro_f
    async def test_asyncgen_universal(self):
        """Asyncgen mw -> universal mw; upgrade"""
        await self._test_asyncgen_base(self.MW_UNIVERSAL, self.MW_ASYNCGEN)


class TestProcessSpiderOutputAsyncGen(TestProcessSpiderOutputSimple):
    """process_spider_output tests for async generator callbacks"""

    async def _callback(self) -> Any:
        for item in super()._callback():
            yield item

    @deferred_f_from_coro_f
    async def test_simple(self):
        """Simple mw; downgrade"""
        await self._test_simple_base(self.MW_SIMPLE, downgrade=True)

    @deferred_f_from_coro_f
    async def test_simple_asyncgen(self):
        """Simple mw -> asyncgen mw; downgrade then upgrade"""
        await self._test_asyncgen_base(self.MW_ASYNCGEN, self.MW_SIMPLE, downgrade=True)

    @deferred_f_from_coro_f
    async def test_universal(self):
        """Universal mw"""
        await self._test_asyncgen_base(self.MW_UNIVERSAL)

    @deferred_f_from_coro_f
    async def test_universal_simple(self):
        """Universal mw -> simple mw; downgrade"""
        await self._test_simple_base(self.MW_SIMPLE, self.MW_UNIVERSAL, downgrade=True)

    @deferred_f_from_coro_f
    async def test_simple_universal(self):
        """Simple mw -> universal mw; downgrade"""
        await self._test_simple_base(self.MW_UNIVERSAL, self.MW_SIMPLE, downgrade=True)


class ProcessSpiderOutputNonIterableMiddleware:
    def process_spider_output(self, response, result, spider):
        return


class ProcessSpiderOutputCoroutineMiddleware:
    async def process_spider_output(self, response, result, spider):
        return result


class TestProcessSpiderOutputInvalidResult(TestBaseAsyncSpiderMiddleware):
    @deferred_f_from_coro_f
    async def test_non_iterable(self):
        with pytest.raises(
            _InvalidOutput,
            match=r"\.process_spider_output must return an iterable, got <class 'NoneType'>",
        ):
            await self._get_middleware_result(ProcessSpiderOutputNonIterableMiddleware)

    @deferred_f_from_coro_f
    async def test_coroutine(self):
        with pytest.raises(
            _InvalidOutput,
            match=r"\.process_spider_output must be an asynchronous generator",
        ):
            await self._get_middleware_result(ProcessSpiderOutputCoroutineMiddleware)


class ProcessStartSimpleMiddleware:
    async def process_start(self, start):
        async for item_or_request in start:
            yield item_or_request


class TestProcessStartSimple(TestBaseAsyncSpiderMiddleware):
    """process_start tests for simple start"""

    ITEM_TYPE = (Request, dict)
    MW_SIMPLE = ProcessStartSimpleMiddleware

    async def _get_processed_start(
        self, *mw_classes: type[Any]
    ) -> AsyncIterator[Any] | None:
        class TestSpider(Spider):
            name = "test"

            async def start(self):
                for i in range(2):
                    yield Request(f"https://example.com/{i}", dont_filter=True)
                yield {"name": "test item"}

        setting = self._construct_mw_setting(*mw_classes)
        self.crawler = get_crawler(
            TestSpider, {"SPIDER_MIDDLEWARES_BASE": {}, "SPIDER_MIDDLEWARES": setting}
        )
        self.spider = self.crawler._create_spider()
        self.mwman = SpiderMiddlewareManager.from_crawler(self.crawler)
        return await self.mwman.process_start(self.spider)

    @deferred_f_from_coro_f
    async def test_simple(self):
        """Simple mw"""
        start = await self._get_processed_start(self.MW_SIMPLE)
        assert isasyncgen(start)
        start_list = await collect_asyncgen(start)
        assert len(start_list) == self.RESULT_COUNT
        assert isinstance(start_list[0], self.ITEM_TYPE)


class UniversalMiddlewareNoSync:
    async def process_spider_output_async(self, response, result, spider):
        yield


class UniversalMiddlewareBothSync:
    def process_spider_output(self, response, result, spider):
        yield

    def process_spider_output_async(self, response, result, spider):
        yield


class UniversalMiddlewareBothAsync:
    async def process_spider_output(self, response, result, spider):
        yield

    async def process_spider_output_async(self, response, result, spider):
        yield


class TestUniversalMiddlewareManager:
    @pytest.fixture
    def mwman(self) -> SpiderMiddlewareManager:
        return SpiderMiddlewareManager()

    def test_simple_mw(self, mwman: SpiderMiddlewareManager) -> None:
        mw = ProcessSpiderOutputSimpleMiddleware()
        mwman._add_middleware(mw)
        assert (
            mwman.methods["process_spider_output"][0] == mw.process_spider_output  # pylint: disable=comparison-with-callable
        )

    def test_async_mw(self, mwman: SpiderMiddlewareManager) -> None:
        mw = ProcessSpiderOutputAsyncGenMiddleware()
        mwman._add_middleware(mw)
        assert (
            mwman.methods["process_spider_output"][0] == mw.process_spider_output  # pylint: disable=comparison-with-callable
        )

    def test_universal_mw(self, mwman: SpiderMiddlewareManager) -> None:
        mw = ProcessSpiderOutputUniversalMiddleware()
        mwman._add_middleware(mw)
        assert mwman.methods["process_spider_output"][0] == (
            mw.process_spider_output,
            mw.process_spider_output_async,
        )

    def test_universal_mw_no_sync(
        self, mwman: SpiderMiddlewareManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        mwman._add_middleware(UniversalMiddlewareNoSync())
        assert (
            "UniversalMiddlewareNoSync has process_spider_output_async"
            " without process_spider_output" in caplog.text
        )
        assert mwman.methods["process_spider_output"][0] is None

    def test_universal_mw_both_sync(
        self, mwman: SpiderMiddlewareManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        mw = UniversalMiddlewareBothSync()
        mwman._add_middleware(mw)
        assert (
            "UniversalMiddlewareBothSync.process_spider_output_async "
            "is not an async generator function" in caplog.text
        )
        assert (
            mwman.methods["process_spider_output"][0] == mw.process_spider_output  # pylint: disable=comparison-with-callable
        )

    def test_universal_mw_both_async(
        self, mwman: SpiderMiddlewareManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        mwman._add_middleware(UniversalMiddlewareBothAsync())
        assert (
            "UniversalMiddlewareBothAsync.process_spider_output "
            "is an async generator function while process_spider_output_async exists"
            in caplog.text
        )
        assert mwman.methods["process_spider_output"][0] is None


class TestBuiltinMiddlewareSimple(TestBaseAsyncSpiderMiddleware):
    ITEM_TYPE = dict
    MW_SIMPLE = ProcessSpiderOutputSimpleMiddleware
    MW_ASYNCGEN = ProcessSpiderOutputAsyncGenMiddleware
    MW_UNIVERSAL = ProcessSpiderOutputUniversalMiddleware

    async def _get_middleware_result(
        self, *mw_classes: type[Any], start_index: int | None = None
    ) -> Any:
        setting = self._construct_mw_setting(*mw_classes, start_index=start_index)
        self.crawler = get_crawler(Spider, {"SPIDER_MIDDLEWARES": setting})
        self.spider = self.crawler._create_spider("foo")
        self.mwman = SpiderMiddlewareManager.from_crawler(self.crawler)
        return await self.mwman.scrape_response_async(
            self._scrape_func, self.response, self.request, self.spider
        )

    @deferred_f_from_coro_f
    async def test_just_builtin(self):
        await self._test_simple_base()

    @deferred_f_from_coro_f
    async def test_builtin_simple(self):
        await self._test_simple_base(self.MW_SIMPLE, start_index=1000)

    @deferred_f_from_coro_f
    async def test_builtin_async(self):
        """Upgrade"""
        await self._test_asyncgen_base(self.MW_ASYNCGEN, start_index=1000)

    @deferred_f_from_coro_f
    async def test_builtin_universal(self):
        await self._test_simple_base(self.MW_UNIVERSAL, start_index=1000)

    @deferred_f_from_coro_f
    async def test_simple_builtin(self):
        await self._test_simple_base(self.MW_SIMPLE)

    @deferred_f_from_coro_f
    async def test_async_builtin(self):
        """Upgrade"""
        await self._test_asyncgen_base(self.MW_ASYNCGEN)

    @deferred_f_from_coro_f
    async def test_universal_builtin(self):
        await self._test_simple_base(self.MW_UNIVERSAL)


class TestBuiltinMiddlewareAsyncGen(TestBuiltinMiddlewareSimple):
    async def _callback(self) -> Any:
        for item in super()._callback():
            yield item

    @deferred_f_from_coro_f
    async def test_just_builtin(self):
        await self._test_asyncgen_base()

    @deferred_f_from_coro_f
    async def test_builtin_simple(self):
        """Downgrade"""
        await self._test_simple_base(self.MW_SIMPLE, downgrade=True, start_index=1000)

    @deferred_f_from_coro_f
    async def test_builtin_async(self):
        await self._test_asyncgen_base(self.MW_ASYNCGEN, start_index=1000)

    @deferred_f_from_coro_f
    async def test_builtin_universal(self):
        await self._test_asyncgen_base(self.MW_UNIVERSAL, start_index=1000)

    @deferred_f_from_coro_f
    async def test_simple_builtin(self):
        """Downgrade"""
        await self._test_simple_base(self.MW_SIMPLE, downgrade=True)

    @deferred_f_from_coro_f
    async def test_async_builtin(self):
        await self._test_asyncgen_base(self.MW_ASYNCGEN)

    @deferred_f_from_coro_f
    async def test_universal_builtin(self):
        await self._test_asyncgen_base(self.MW_UNIVERSAL)


class TestProcessSpiderException(TestBaseAsyncSpiderMiddleware):
    ITEM_TYPE = dict
    MW_SIMPLE = ProcessSpiderOutputSimpleMiddleware
    MW_ASYNCGEN = ProcessSpiderOutputAsyncGenMiddleware
    MW_UNIVERSAL = ProcessSpiderOutputUniversalMiddleware
    MW_EXC_SIMPLE = ProcessSpiderExceptionSimpleIterableMiddleware
    MW_EXC_ASYNCGEN = ProcessSpiderExceptionAsyncIteratorMiddleware

    def _callback(self) -> Any:
        1 / 0

    async def _test_asyncgen_nodowngrade(self, *mw_classes: type[Any]) -> None:
        with pytest.raises(
            _InvalidOutput, match="Async iterable returned from .+ cannot be downgraded"
        ):
            await self._get_middleware_result(*mw_classes)

    @deferred_f_from_coro_f
    async def test_exc_simple(self):
        """Simple exc mw"""
        await self._test_simple_base(self.MW_EXC_SIMPLE)

    @deferred_f_from_coro_f
    async def test_exc_async(self):
        """Async exc mw"""
        await self._test_asyncgen_base(self.MW_EXC_ASYNCGEN)

    @deferred_f_from_coro_f
    async def test_exc_simple_simple(self):
        """Simple exc mw -> simple output mw"""
        await self._test_simple_base(self.MW_SIMPLE, self.MW_EXC_SIMPLE)

    @deferred_f_from_coro_f
    async def test_exc_async_async(self):
        """Async exc mw -> async output mw"""
        await self._test_asyncgen_base(self.MW_ASYNCGEN, self.MW_EXC_ASYNCGEN)

    @deferred_f_from_coro_f
    async def test_exc_simple_async(self):
        """Simple exc mw -> async output mw; upgrade"""
        await self._test_asyncgen_base(self.MW_ASYNCGEN, self.MW_EXC_SIMPLE)

    @deferred_f_from_coro_f
    async def test_exc_async_simple(self):
        """Async exc mw -> simple output mw; cannot work as downgrading is not supported"""
        await self._test_asyncgen_nodowngrade(self.MW_SIMPLE, self.MW_EXC_ASYNCGEN)
