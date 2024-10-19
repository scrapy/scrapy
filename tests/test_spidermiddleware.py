from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from unittest import mock

from testfixtures import LogCapture
from twisted.internet import defer
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase

from scrapy.core.spidermw import SpiderMiddlewareManager
from scrapy.exceptions import _InvalidOutput
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.utils.asyncgen import collect_asyncgen
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.test import get_crawler


class SpiderMiddlewareTestCase(TestCase):
    def setUp(self):
        self.request = Request("http://example.com/index.html")
        self.response = Response(self.request.url, request=self.request)
        self.crawler = get_crawler(Spider, {"SPIDER_MIDDLEWARES_BASE": {}})
        self.spider = self.crawler._create_spider("foo")
        self.mwman = SpiderMiddlewareManager.from_crawler(self.crawler)

    def _scrape_response(self):
        """Execute spider mw manager's scrape_response method and return the result.
        Raise exception in case of failure.
        """
        scrape_func = mock.MagicMock()
        dfd = self.mwman.scrape_response(
            scrape_func, self.response, self.request, self.spider
        )
        # catch deferred result and return the value
        results = []
        dfd.addBoth(results.append)
        self._wait(dfd)
        ret = results[0]
        return ret


class ProcessSpiderInputInvalidOutput(SpiderMiddlewareTestCase):
    """Invalid return value for process_spider_input method"""

    def test_invalid_process_spider_input(self):
        class InvalidProcessSpiderInputMiddleware:
            def process_spider_input(self, response, spider):
                return 1

        self.mwman._add_middleware(InvalidProcessSpiderInputMiddleware())
        result = self._scrape_response()
        self.assertIsInstance(result, Failure)
        self.assertIsInstance(result.value, _InvalidOutput)


class ProcessSpiderOutputInvalidOutput(SpiderMiddlewareTestCase):
    """Invalid return value for process_spider_output method"""

    def test_invalid_process_spider_output(self):
        class InvalidProcessSpiderOutputMiddleware:
            def process_spider_output(self, response, result, spider):
                return 1

        self.mwman._add_middleware(InvalidProcessSpiderOutputMiddleware())
        result = self._scrape_response()
        self.assertIsInstance(result, Failure)
        self.assertIsInstance(result.value, _InvalidOutput)


class ProcessSpiderExceptionInvalidOutput(SpiderMiddlewareTestCase):
    """Invalid return value for process_spider_exception method"""

    def test_invalid_process_spider_exception(self):
        class InvalidProcessSpiderOutputExceptionMiddleware:
            def process_spider_exception(self, response, exception, spider):
                return 1

        class RaiseExceptionProcessSpiderOutputMiddleware:
            def process_spider_output(self, response, result, spider):
                raise Exception()

        self.mwman._add_middleware(InvalidProcessSpiderOutputExceptionMiddleware())
        self.mwman._add_middleware(RaiseExceptionProcessSpiderOutputMiddleware())
        result = self._scrape_response()
        self.assertIsInstance(result, Failure)
        self.assertIsInstance(result.value, _InvalidOutput)


class ProcessSpiderExceptionReRaise(SpiderMiddlewareTestCase):
    """Re raise the exception by returning None"""

    def test_process_spider_exception_return_none(self):
        class ProcessSpiderExceptionReturnNoneMiddleware:
            def process_spider_exception(self, response, exception, spider):
                return None

        class RaiseExceptionProcessSpiderOutputMiddleware:
            def process_spider_output(self, response, result, spider):
                1 / 0

        self.mwman._add_middleware(ProcessSpiderExceptionReturnNoneMiddleware())
        self.mwman._add_middleware(RaiseExceptionProcessSpiderOutputMiddleware())
        result = self._scrape_response()
        self.assertIsInstance(result, Failure)
        self.assertIsInstance(result.value, ZeroDivisionError)


class BaseAsyncSpiderMiddlewareTestCase(SpiderMiddlewareTestCase):
    """Helpers for testing sync, async and mixed middlewares.

    Should work for process_spider_output and, when it's supported, process_start_requests.
    """

    ITEM_TYPE: type | tuple
    RESULT_COUNT = 3  # to simplify checks, let everything return 3 objects

    @staticmethod
    def _construct_mw_setting(*mw_classes, start_index: int | None = None):
        if start_index is None:
            start_index = 10
        return {i: c for c, i in enumerate(mw_classes, start=start_index)}

    def _scrape_func(self, *args, **kwargs):
        yield {"foo": 1}
        yield {"foo": 2}
        yield {"foo": 3}

    @defer.inlineCallbacks
    def _get_middleware_result(self, *mw_classes, start_index: int | None = None):
        setting = self._construct_mw_setting(*mw_classes, start_index=start_index)
        self.crawler = get_crawler(
            Spider, {"SPIDER_MIDDLEWARES_BASE": {}, "SPIDER_MIDDLEWARES": setting}
        )
        self.spider = self.crawler._create_spider("foo")
        self.mwman = SpiderMiddlewareManager.from_crawler(self.crawler)
        result = yield self.mwman.scrape_response(
            self._scrape_func, self.response, self.request, self.spider
        )
        return result

    @defer.inlineCallbacks
    def _test_simple_base(
        self, *mw_classes, downgrade: bool = False, start_index: int | None = None
    ):
        with LogCapture() as log:
            result = yield self._get_middleware_result(
                *mw_classes, start_index=start_index
            )
        self.assertIsInstance(result, Iterable)
        result_list = list(result)
        self.assertEqual(len(result_list), self.RESULT_COUNT)
        self.assertIsInstance(result_list[0], self.ITEM_TYPE)
        self.assertEqual("downgraded to a non-async" in str(log), downgrade)

    @defer.inlineCallbacks
    def _test_asyncgen_base(
        self, *mw_classes, downgrade: bool = False, start_index: int | None = None
    ):
        with LogCapture() as log:
            result = yield self._get_middleware_result(
                *mw_classes, start_index=start_index
            )
        self.assertIsInstance(result, AsyncIterator)
        result_list = yield deferred_from_coro(collect_asyncgen(result))
        self.assertEqual(len(result_list), self.RESULT_COUNT)
        self.assertIsInstance(result_list[0], self.ITEM_TYPE)
        self.assertEqual("downgraded to a non-async" in str(log), downgrade)


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


class ProcessSpiderExceptionAsyncIterableMiddleware:
    async def process_spider_exception(self, response, exception, spider):
        yield {"foo": 1}
        d = defer.Deferred()
        from twisted.internet import reactor

        reactor.callLater(0, d.callback, None)
        await maybe_deferred_to_future(d)
        yield {"foo": 2}
        yield {"foo": 3}


class ProcessSpiderOutputSimple(BaseAsyncSpiderMiddlewareTestCase):
    """process_spider_output tests for simple callbacks"""

    ITEM_TYPE = dict
    MW_SIMPLE = ProcessSpiderOutputSimpleMiddleware
    MW_ASYNCGEN = ProcessSpiderOutputAsyncGenMiddleware
    MW_UNIVERSAL = ProcessSpiderOutputUniversalMiddleware

    def test_simple(self):
        """Simple mw"""
        return self._test_simple_base(self.MW_SIMPLE)

    def test_asyncgen(self):
        """Asyncgen mw; upgrade"""
        return self._test_asyncgen_base(self.MW_ASYNCGEN)

    def test_simple_asyncgen(self):
        """Simple mw -> asyncgen mw; upgrade"""
        return self._test_asyncgen_base(self.MW_ASYNCGEN, self.MW_SIMPLE)

    def test_asyncgen_simple(self):
        """Asyncgen mw -> simple mw; upgrade then downgrade"""
        return self._test_simple_base(self.MW_SIMPLE, self.MW_ASYNCGEN, downgrade=True)

    def test_universal(self):
        """Universal mw"""
        return self._test_simple_base(self.MW_UNIVERSAL)

    def test_universal_simple(self):
        """Universal mw -> simple mw"""
        return self._test_simple_base(self.MW_SIMPLE, self.MW_UNIVERSAL)

    def test_simple_universal(self):
        """Simple mw -> universal mw"""
        return self._test_simple_base(self.MW_UNIVERSAL, self.MW_SIMPLE)

    def test_universal_asyncgen(self):
        """Universal mw -> asyncgen mw; upgrade"""
        return self._test_asyncgen_base(self.MW_ASYNCGEN, self.MW_UNIVERSAL)

    def test_asyncgen_universal(self):
        """Asyncgen mw -> universal mw; upgrade"""
        return self._test_asyncgen_base(self.MW_UNIVERSAL, self.MW_ASYNCGEN)


class ProcessSpiderOutputAsyncGen(ProcessSpiderOutputSimple):
    """process_spider_output tests for async generator callbacks"""

    async def _scrape_func(self, *args, **kwargs):
        for item in super()._scrape_func():
            yield item

    def test_simple(self):
        """Simple mw; downgrade"""
        return self._test_simple_base(self.MW_SIMPLE, downgrade=True)

    def test_simple_asyncgen(self):
        """Simple mw -> asyncgen mw; downgrade then upgrade"""
        return self._test_asyncgen_base(
            self.MW_ASYNCGEN, self.MW_SIMPLE, downgrade=True
        )

    def test_universal(self):
        """Universal mw"""
        return self._test_asyncgen_base(self.MW_UNIVERSAL)

    def test_universal_simple(self):
        """Universal mw -> simple mw; downgrade"""
        return self._test_simple_base(self.MW_SIMPLE, self.MW_UNIVERSAL, downgrade=True)

    def test_simple_universal(self):
        """Simple mw -> universal mw; downgrade"""
        return self._test_simple_base(self.MW_UNIVERSAL, self.MW_SIMPLE, downgrade=True)


class ProcessSpiderOutputNonIterableMiddleware:
    def process_spider_output(self, response, result, spider):
        return


class ProcessSpiderOutputCoroutineMiddleware:
    async def process_spider_output(self, response, result, spider):
        results = []
        for r in result:
            results.append(r)
        return results


class ProcessSpiderOutputInvalidResult(BaseAsyncSpiderMiddlewareTestCase):
    @defer.inlineCallbacks
    def test_non_iterable(self):
        with self.assertRaisesRegex(
            _InvalidOutput,
            (
                r"\.process_spider_output must return an iterable, got <class "
                r"'NoneType'>"
            ),
        ):
            yield self._get_middleware_result(
                ProcessSpiderOutputNonIterableMiddleware,
            )

    @defer.inlineCallbacks
    def test_coroutine(self):
        with self.assertRaisesRegex(
            _InvalidOutput,
            r"\.process_spider_output must be an asynchronous generator",
        ):
            yield self._get_middleware_result(
                ProcessSpiderOutputCoroutineMiddleware,
            )


class ProcessStartRequestsSimpleMiddleware:
    def process_start_requests(self, start_requests, spider):
        yield from start_requests


class ProcessStartRequestsSimple(BaseAsyncSpiderMiddlewareTestCase):
    """process_start_requests tests for simple start_requests"""

    ITEM_TYPE = (Request, dict)
    MW_SIMPLE = ProcessStartRequestsSimpleMiddleware

    def _start_requests(self):
        for i in range(2):
            yield Request(f"https://example.com/{i}", dont_filter=True)
        yield {"name": "test item"}

    @defer.inlineCallbacks
    def _get_middleware_result(self, *mw_classes, start_index: int | None = None):
        setting = self._construct_mw_setting(*mw_classes, start_index=start_index)
        self.crawler = get_crawler(
            Spider, {"SPIDER_MIDDLEWARES_BASE": {}, "SPIDER_MIDDLEWARES": setting}
        )
        self.spider = self.crawler._create_spider("foo")
        self.mwman = SpiderMiddlewareManager.from_crawler(self.crawler)
        start_requests = iter(self._start_requests())
        results = yield self.mwman.process_start_requests(start_requests, self.spider)
        return results

    def test_simple(self):
        """Simple mw"""
        return self._test_simple_base(self.MW_SIMPLE)


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


class UniversalMiddlewareManagerTest(TestCase):
    def setUp(self):
        self.mwman = SpiderMiddlewareManager()

    def test_simple_mw(self):
        mw = ProcessSpiderOutputSimpleMiddleware
        self.mwman._add_middleware(mw)
        self.assertEqual(
            self.mwman.methods["process_spider_output"][0], mw.process_spider_output
        )

    def test_async_mw(self):
        mw = ProcessSpiderOutputAsyncGenMiddleware
        self.mwman._add_middleware(mw)
        self.assertEqual(
            self.mwman.methods["process_spider_output"][0], mw.process_spider_output
        )

    def test_universal_mw(self):
        mw = ProcessSpiderOutputUniversalMiddleware
        self.mwman._add_middleware(mw)
        self.assertEqual(
            self.mwman.methods["process_spider_output"][0],
            (mw.process_spider_output, mw.process_spider_output_async),
        )

    def test_universal_mw_no_sync(self):
        with LogCapture() as log:
            self.mwman._add_middleware(UniversalMiddlewareNoSync)
        self.assertIn(
            "UniversalMiddlewareNoSync has process_spider_output_async"
            " without process_spider_output",
            str(log),
        )
        self.assertEqual(self.mwman.methods["process_spider_output"][0], None)

    def test_universal_mw_both_sync(self):
        mw = UniversalMiddlewareBothSync
        with LogCapture() as log:
            self.mwman._add_middleware(mw)
        self.assertIn(
            "UniversalMiddlewareBothSync.process_spider_output_async "
            "is not an async generator function",
            str(log),
        )
        self.assertEqual(
            self.mwman.methods["process_spider_output"][0], mw.process_spider_output
        )

    def test_universal_mw_both_async(self):
        with LogCapture() as log:
            self.mwman._add_middleware(UniversalMiddlewareBothAsync)
        self.assertIn(
            "UniversalMiddlewareBothAsync.process_spider_output "
            "is an async generator function while process_spider_output_async exists",
            str(log),
        )
        self.assertEqual(self.mwman.methods["process_spider_output"][0], None)


class BuiltinMiddlewareSimpleTest(BaseAsyncSpiderMiddlewareTestCase):
    ITEM_TYPE = dict
    MW_SIMPLE = ProcessSpiderOutputSimpleMiddleware
    MW_ASYNCGEN = ProcessSpiderOutputAsyncGenMiddleware
    MW_UNIVERSAL = ProcessSpiderOutputUniversalMiddleware

    @defer.inlineCallbacks
    def _get_middleware_result(self, *mw_classes, start_index: int | None = None):
        setting = self._construct_mw_setting(*mw_classes, start_index=start_index)
        self.crawler = get_crawler(Spider, {"SPIDER_MIDDLEWARES": setting})
        self.spider = self.crawler._create_spider("foo")
        self.mwman = SpiderMiddlewareManager.from_crawler(self.crawler)
        result = yield self.mwman.scrape_response(
            self._scrape_func, self.response, self.request, self.spider
        )
        return result

    def test_just_builtin(self):
        return self._test_simple_base()

    def test_builtin_simple(self):
        return self._test_simple_base(self.MW_SIMPLE, start_index=1000)

    def test_builtin_async(self):
        """Upgrade"""
        return self._test_asyncgen_base(self.MW_ASYNCGEN, start_index=1000)

    def test_builtin_universal(self):
        return self._test_simple_base(self.MW_UNIVERSAL, start_index=1000)

    def test_simple_builtin(self):
        return self._test_simple_base(self.MW_SIMPLE)

    def test_async_builtin(self):
        """Upgrade"""
        return self._test_asyncgen_base(self.MW_ASYNCGEN)

    def test_universal_builtin(self):
        return self._test_simple_base(self.MW_UNIVERSAL)


class BuiltinMiddlewareAsyncGenTest(BuiltinMiddlewareSimpleTest):
    async def _scrape_func(self, *args, **kwargs):
        for item in super()._scrape_func():
            yield item

    def test_just_builtin(self):
        return self._test_asyncgen_base()

    def test_builtin_simple(self):
        """Downgrade"""
        return self._test_simple_base(self.MW_SIMPLE, downgrade=True, start_index=1000)

    def test_builtin_async(self):
        return self._test_asyncgen_base(self.MW_ASYNCGEN, start_index=1000)

    def test_builtin_universal(self):
        return self._test_asyncgen_base(self.MW_UNIVERSAL, start_index=1000)

    def test_simple_builtin(self):
        """Downgrade"""
        return self._test_simple_base(self.MW_SIMPLE, downgrade=True)

    def test_async_builtin(self):
        return self._test_asyncgen_base(self.MW_ASYNCGEN)

    def test_universal_builtin(self):
        return self._test_asyncgen_base(self.MW_UNIVERSAL)


class ProcessSpiderExceptionTest(BaseAsyncSpiderMiddlewareTestCase):
    ITEM_TYPE = dict
    MW_SIMPLE = ProcessSpiderOutputSimpleMiddleware
    MW_ASYNCGEN = ProcessSpiderOutputAsyncGenMiddleware
    MW_UNIVERSAL = ProcessSpiderOutputUniversalMiddleware
    MW_EXC_SIMPLE = ProcessSpiderExceptionSimpleIterableMiddleware
    MW_EXC_ASYNCGEN = ProcessSpiderExceptionAsyncIterableMiddleware

    def _scrape_func(self, *args, **kwargs):
        1 / 0

    @defer.inlineCallbacks
    def _test_asyncgen_nodowngrade(self, *mw_classes):
        with self.assertRaisesRegex(
            _InvalidOutput, "Async iterable returned from .+ cannot be downgraded"
        ):
            yield self._get_middleware_result(*mw_classes)

    def test_exc_simple(self):
        """Simple exc mw"""
        return self._test_simple_base(self.MW_EXC_SIMPLE)

    def test_exc_async(self):
        """Async exc mw"""
        return self._test_asyncgen_base(self.MW_EXC_ASYNCGEN)

    def test_exc_simple_simple(self):
        """Simple exc mw -> simple output mw"""
        return self._test_simple_base(self.MW_SIMPLE, self.MW_EXC_SIMPLE)

    def test_exc_async_async(self):
        """Async exc mw -> async output mw"""
        return self._test_asyncgen_base(self.MW_ASYNCGEN, self.MW_EXC_ASYNCGEN)

    def test_exc_simple_async(self):
        """Simple exc mw -> async output mw; upgrade"""
        return self._test_asyncgen_base(self.MW_ASYNCGEN, self.MW_EXC_SIMPLE)

    def test_exc_async_simple(self):
        """Async exc mw -> simple output mw; cannot work as downgrading is not supported"""
        return self._test_asyncgen_nodowngrade(self.MW_SIMPLE, self.MW_EXC_ASYNCGEN)
