import collections.abc
from unittest import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase
from twisted.python.failure import Failure

from scrapy.spiders import Spider
from scrapy.http import Request, Response
from scrapy.exceptions import _InvalidOutput
from scrapy.utils.asyncgen import _process_iterable_universal, as_async_generator, collect_asyncgen
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.test import get_crawler
from scrapy.core.spidermw import SpiderMiddlewareManager


class SpiderMiddlewareTestCase(TestCase):

    def setUp(self):
        self.request = Request('http://example.com/index.html')
        self.response = Response(self.request.url, request=self.request)
        self.crawler = get_crawler(Spider, {'SPIDER_MIDDLEWARES_BASE': {}})
        self.spider = self.crawler._create_spider('foo')
        self.mwman = SpiderMiddlewareManager.from_crawler(self.crawler)

    def _scrape_response(self):
        """Execute spider mw manager's scrape_response method and return the result.
        Raise exception in case of failure.
        """
        scrape_func = mock.MagicMock()
        dfd = self.mwman.scrape_response(scrape_func, self.response, self.request, self.spider)
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
    """ Helpers for testing sync, async and mixed middlewares.

    Should work for process_spider_output and, when it's supported, process_start_requests.
    """

    RESULT_COUNT = 3  # to simplify checks, let everything return 3 objects

    @defer.inlineCallbacks
    def _get_middleware_result(self, *mw_classes):
        for mw_cls in mw_classes:
            self.mwman._add_middleware(mw_cls())
        result = yield self.mwman.scrape_response(self._scrape_func, self.response, self.request, self.spider)
        return result

    @defer.inlineCallbacks
    def _test_simple_base(self, *mw_classes):
        result = yield self._get_middleware_result(*mw_classes)
        self.assertIsInstance(result, collections.abc.Iterable)
        result_list = list(result)
        self.assertEqual(len(result_list), self.RESULT_COUNT)
        self.assertIsInstance(result_list[0], self.ITEM_TYPE)

    @defer.inlineCallbacks
    def _test_asyncgen_base(self, *mw_classes):
        result = yield self._get_middleware_result(*mw_classes)
        self.assertIsInstance(result, collections.abc.AsyncIterator)
        result_list = yield deferred_from_coro(collect_asyncgen(result))
        self.assertEqual(len(result_list), self.RESULT_COUNT)
        self.assertIsInstance(result_list[0], self.ITEM_TYPE)

    @defer.inlineCallbacks
    def _test_asyncgen_fail(self, *mw_classes):
        with self.assertRaisesRegex(TypeError, "Synchronous .+ called with an async iterable"):
            yield self._get_middleware_result(*mw_classes)


class ProcessSpiderOutputSimpleMiddleware:
    def process_spider_output(self, response, result, spider):
        for r in result:
            yield r


class ProcessSpiderOutputAsyncGenMiddleware:
    async def process_spider_output(self, response, result, spider):
        async for r in as_async_generator(result):
            yield r


class ProcessSpiderOutputUniversalMiddleware:
    def process_spider_output(self, response, result, spider):
        @_process_iterable_universal
        async def process(result):
            async for r in result:
                yield r
        return process(result)


class ProcessSpiderOutputSimple(BaseAsyncSpiderMiddlewareTestCase):
    """ process_spider_output tests for simple callbacks"""

    ITEM_TYPE = dict
    MW_SIMPLE = ProcessSpiderOutputSimpleMiddleware
    MW_ASYNCGEN = ProcessSpiderOutputAsyncGenMiddleware
    MW_UNIVERSAL = ProcessSpiderOutputUniversalMiddleware

    def _scrape_func(self, *args, **kwargs):
        yield {'foo': 1}
        yield {'foo': 2}
        yield {'foo': 3}

    def test_simple(self):
        """ Simple mw """
        return self._test_simple_base(self.MW_SIMPLE)

    def test_asyncgen(self):
        """ Asyncgen mw """
        return self._test_asyncgen_base(self.MW_ASYNCGEN)

    def test_simple_asyncgen(self):
        """ Simple mw -> asyncgen mw """
        return self._test_asyncgen_base(self.MW_ASYNCGEN,
                                        self.MW_SIMPLE)

    def test_asyncgen_simple(self):
        """ Asyncgen mw -> simple mw; cannot work """
        return self._test_asyncgen_fail(self.MW_SIMPLE,
                                        self.MW_ASYNCGEN)

    def test_universal(self):
        """ Universal mw """
        return self._test_simple_base(self.MW_UNIVERSAL)

    def test_universal_simple(self):
        """ Universal mw -> simple mw """
        return self._test_simple_base(self.MW_SIMPLE,
                                      self.MW_UNIVERSAL)

    def test_simple_universal(self):
        """ Simple mw -> universal mw """
        return self._test_simple_base(self.MW_UNIVERSAL,
                                      self.MW_SIMPLE)

    def test_universal_asyncgen(self):
        """ Universal mw -> asyncgen mw """
        return self._test_asyncgen_base(self.MW_ASYNCGEN,
                                        self.MW_UNIVERSAL)

    def test_asyncgen_universal(self):
        """ Asyncgen mw -> universal mw """
        return self._test_asyncgen_base(self.MW_UNIVERSAL,
                                        self.MW_ASYNCGEN)


class ProcessSpiderOutputAsyncGen(ProcessSpiderOutputSimple):
    """ process_spider_output tests for async generator callbacks """

    async def _scrape_func(self, *args, **kwargs):
        for item in super()._scrape_func():
            yield item

    def test_simple(self):
        """ Simple mw; cannot work """
        return self._test_asyncgen_fail(self.MW_SIMPLE)

    def test_simple_asyncgen(self):
        """ Simple mw -> asyncgen mw; cannot work """
        return self._test_asyncgen_fail(self.MW_ASYNCGEN,
                                        self.MW_SIMPLE)

    def test_universal(self):
        """ Universal mw """
        return self._test_asyncgen_base(self.MW_UNIVERSAL)

    def test_universal_simple(self):
        """ Universal mw -> simple mw; cannot work """
        return self._test_asyncgen_fail(self.MW_SIMPLE,
                                        self.MW_UNIVERSAL)

    def test_simple_universal(self):
        """ Simple mw -> universal mw; cannot work """
        return self._test_asyncgen_fail(self.MW_UNIVERSAL,
                                        self.MW_SIMPLE)


class ProcessStartRequestsSimpleMiddleware:
    def process_start_requests(self, start_requests, spider):
        for r in start_requests:
            yield r


class ProcessStartRequestsSimple(BaseAsyncSpiderMiddlewareTestCase):
    """ process_start_requests tests for simple start_requests"""

    ITEM_TYPE = Request
    MW_SIMPLE = ProcessStartRequestsSimpleMiddleware

    def _start_requests(self):
        for i in range(3):
            yield Request(f'https://example.com/{i}', dont_filter=True)

    @defer.inlineCallbacks
    def _get_middleware_result(self, *mw_classes):
        for mw_cls in mw_classes:
            self.mwman._add_middleware(mw_cls())
        start_requests = iter(self._start_requests())
        results = yield self.mwman.process_start_requests(start_requests, self.spider)
        return results

    def test_simple(self):
        """ Simple mw """
        self._test_simple_base(self.MW_SIMPLE)
