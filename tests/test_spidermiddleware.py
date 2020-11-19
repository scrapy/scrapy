import collections
import inspect
from unittest import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase
from twisted.python.failure import Failure

from scrapy.spiders import Spider
from scrapy.http import Request, Response
from scrapy.exceptions import _InvalidOutput
from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.test import get_crawler
from scrapy.core.spidermw import SpiderMiddlewareManager
from tests.test_engine import StartRequestsAsyncDefSpider, StartRequestsAsyncGenSpider


class SpiderMiddlewareTestCase(TestCase):

    def setUp(self):
        self.request = Request('http://example.com/index.html')
        self.response = Response(self.request.url, request=self.request)
        self.crawler = get_crawler(Spider)
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


class ProcessStartRequestsSimpleMiddleware:
    def process_start_requests(self, start_requests, spider):
        for r in start_requests:
            yield r


class ProcessStartRequestsAsyncDefMiddleware:
    async def process_start_requests(self, start_requests, spider):
        return start_requests


class ProcessStartRequestsAsyncGenMiddleware:
    async def process_start_requests(self, start_requests, spider):
        async for r in as_async_generator(start_requests):
            yield r


class ProcessStartRequestsSimple(TestCase):
    """ process_start_requests tests for simple start_requests"""

    spider_cls = Spider

    @defer.inlineCallbacks
    def _get_processed_start_requests(self, *mw_classes):
        crawler = get_crawler(self.spider_cls)
        start_urls = ['https://example.com/%d' % i for i in range(3)]
        crawler.spider = crawler._create_spider('foo', start_urls=start_urls)
        mwman = SpiderMiddlewareManager.from_crawler(crawler)
        for mw_cls in mw_classes:
            mwman._add_middleware(mw_cls())
        start_requests = yield crawler.call_start_requests()
        processed_start_requests = yield mwman.process_start_requests(start_requests, crawler.spider)
        return processed_start_requests

    def assertAsyncGeneratorNotIterable(self, processed_start_requests):
        with self.assertRaisesRegex(TypeError, "'async_generator' object is not iterable"):
            list(processed_start_requests)

    @defer.inlineCallbacks
    def _test_simple_base(self, *mw_classes):
        processed_start_requests = yield self._get_processed_start_requests(*mw_classes)
        self.assertIsInstance(processed_start_requests, collections.abc.Iterable)
        start_requests_list = list(processed_start_requests)
        self.assertEqual(len(start_requests_list), 3)
        self.assertIsInstance(start_requests_list[0], Request)

    @defer.inlineCallbacks
    def _test_asyncgen_base(self, *mw_classes):
        processed_start_requests = yield self._get_processed_start_requests(*mw_classes)
        self.assertTrue(inspect.isasyncgen(processed_start_requests))
        start_requests_list = yield deferred_from_coro(collect_asyncgen(processed_start_requests))
        self.assertEqual(len(start_requests_list), 3)
        self.assertIsInstance(start_requests_list[0], Request)

    @defer.inlineCallbacks
    def test_simple(self):
        """ Simple mw """
        yield self._test_simple_base(ProcessStartRequestsSimpleMiddleware)

    @defer.inlineCallbacks
    def test_asyncdef(self):
        """ Async def mw """
        yield self._test_simple_base(ProcessStartRequestsAsyncDefMiddleware)

    @defer.inlineCallbacks
    def test_asyncgen(self):
        """ Asyncgen mw """
        yield self._test_asyncgen_base(ProcessStartRequestsAsyncGenMiddleware)

    @defer.inlineCallbacks
    def test_simple_asyncgen(self):
        """ Simple mw -> asyncgen mw """
        yield self._test_asyncgen_base(ProcessStartRequestsAsyncGenMiddleware,
                                       ProcessStartRequestsSimpleMiddleware)

    @defer.inlineCallbacks
    def test_asyncgen_simple(self):
        """ Asyncgen mw -> simple mw; cannot work """
        processed_start_requests = yield self._get_processed_start_requests(
            ProcessStartRequestsSimpleMiddleware,
            ProcessStartRequestsAsyncGenMiddleware)
        self.assertTrue(inspect.isgenerator(processed_start_requests))
        self.assertAsyncGeneratorNotIterable(processed_start_requests)


class ProcessStartRequestsAsyncDef(ProcessStartRequestsSimple):
    """ process_start_requests tests for async def start_requests """

    spider_cls = StartRequestsAsyncDefSpider


class ProcessStartRequestsAsyncGen(ProcessStartRequestsSimple):
    """ process_start_requests tests for async generator start_requests """

    def __init__(self, methodName='runTest'):
        super().__init__(methodName)
        self.spider_cls = StartRequestsAsyncGenSpider

    @defer.inlineCallbacks
    def test_simple(self):
        """ Simple mw; cannot work """
        processed_start_requests = yield self._get_processed_start_requests(
            ProcessStartRequestsSimpleMiddleware)
        self.assertTrue(inspect.isgenerator(processed_start_requests))
        self.assertAsyncGeneratorNotIterable(processed_start_requests)

    @defer.inlineCallbacks
    def test_asyncdef(self):
        """ Async def mw """
        yield self._test_asyncgen_base(ProcessStartRequestsAsyncDefMiddleware)

    @defer.inlineCallbacks
    def test_simple_asyncgen(self):
        """ Simple mw -> asyncgen mw; cannot work """
        processed_start_requests = yield self._get_processed_start_requests(
            ProcessStartRequestsAsyncGenMiddleware,
            ProcessStartRequestsSimpleMiddleware)
        self.assertTrue(inspect.isasyncgen(processed_start_requests))
        self.assertAsyncGeneratorNotIterable(processed_start_requests)
