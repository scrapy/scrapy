from unittest import mock

from twisted.trial.unittest import TestCase
from twisted.python.failure import Failure

from scrapy.spiders import Spider
from scrapy.http import Request, Response
from scrapy.exceptions import _InvalidOutput
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
