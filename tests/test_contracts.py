from unittest import TextTestRunner

from twisted.internet.defer import TimeoutError, CancelledError
from twisted.python.failure import Failure
from twisted.trial import unittest

from scrapy.commands.check import TextTestResult
from scrapy.spidermiddlewares.httperror import HttpError
from scrapy.spiders import Spider
from scrapy.http import Request
from scrapy.item import Item, Field
from scrapy.contracts import ContractsManager
from scrapy.contracts.default import (
    UrlContract,
    ReturnsContract,
    ScrapesContract,
    IgnoreContract)


class TestItem(Item):
    name = Field()
    url = Field()


class ResponseMock(object):
    url = 'http://scrapy.org'


class TestSpider(Spider):
    name = 'demo_spider'

    def returns_request(self, response):
        """ method which returns request
        @url http://scrapy.org
        @returns requests 1
        """
        return Request('http://scrapy.org', callback=self.returns_item)

    def returns_item(self, response):
        """ method which returns item
        @url http://scrapy.org
        @returns items 1 1
        """
        return TestItem(url=response.url)

    def returns_dict_item(self, response):
        """ method which returns item
        @url http://scrapy.org
        @returns items 1 1
        """
        return {"url": response.url}

    def returns_fail(self, response):
        """ method which returns item
        @url http://scrapy.org
        @returns items 0 0
        """
        return TestItem(url=response.url)

    def returns_dict_fail(self, response):
        """ method which returns item
        @url http://scrapy.org
        @returns items 0 0
        """
        return {'url': response.url}

    def scrapes_item_ok(self, response):
        """ returns item with name and url
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        return TestItem(name='test', url=response.url)

    def scrapes_dict_item_ok(self, response):
        """ returns item with name and url
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        return {'name': 'test', 'url': response.url}

    def scrapes_item_fail(self, response):
        """ returns item with no name
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        return TestItem(url=response.url)

    def scrapes_dict_item_fail(self, response):
        """ returns item with no name
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        return {'url': response.url}

    def parse_no_url(self, response):
        """ method with no url
        @returns items 1 1
        """
        pass

    def ignore_timeout_error(self, response):
        """ should return an item but ignore TimeoutError if occurs
        @url http://scrapy.org
        @ignore TimeoutError
        @returns items 1 1
        """
        return TestItem(url=response.url)

    def ignore_timeout_and_http_errors(self, response):
        """ should return an item but ignore TimeoutError and HttpError if occurs
        @url http://scrapy.org
        @ignore TimeoutError HttpError
        @returns items 1 1
        """
        return TestItem(url=response.url)


class ContractsManagerTest(unittest.TestCase):
    contracts = [UrlContract, ReturnsContract, ScrapesContract, IgnoreContract]

    def setUp(self):
        self.conman = ContractsManager(self.contracts)
        # Change the verbosity to display the test results
        runner = TextTestRunner(verbosity=1)
        self.results = TextTestResult(runner.stream, runner.descriptions, runner.verbosity)

    def should_succeed(self):
        self.assertFalse(self.results.failures)
        self.assertFalse(self.results.errors)

    def should_fail(self):
        self.assertTrue(self.results.failures)
        self.assertFalse(self.results.errors)

    def should_error(self):
        self.assertFalse(self.results.failures)
        self.assertTrue(self.results.errors)

    def test_contracts(self):
        spider = TestSpider()

        # extract contracts correctly
        contracts = self.conman.extract_contracts(spider.returns_request)
        self.assertEqual(len(contracts), 2)
        self.assertEqual(frozenset(type(x) for x in contracts),
            frozenset([UrlContract, ReturnsContract]))

        # returns request for valid method
        request = self.conman.from_method(spider.returns_request, self.results)
        self.assertNotEqual(request, None)

        # no request for missing url
        request = self.conman.from_method(spider.parse_no_url, self.results)
        self.assertEqual(request, None)

    def test_returns(self):
        spider = TestSpider()
        response = ResponseMock()

        # returns_item
        request = self.conman.from_method(spider.returns_item, self.results)
        request.callback(response)
        self.should_succeed()

        # returns_dict_item
        request = self.conman.from_method(spider.returns_dict_item, self.results)
        request.callback(response)
        self.should_succeed()

        # returns_request
        request = self.conman.from_method(spider.returns_request, self.results)
        request.callback(response)
        self.should_succeed()

        # returns_fail
        request = self.conman.from_method(spider.returns_fail, self.results)
        request.callback(response)
        self.should_fail()

        # returns_dict_fail
        request = self.conman.from_method(spider.returns_dict_fail, self.results)
        request.callback(response)
        self.should_fail()

    def test_scrapes(self):
        spider = TestSpider()
        response = ResponseMock()

        # scrapes_item_ok
        request = self.conman.from_method(spider.scrapes_item_ok, self.results)
        request.callback(response)
        self.should_succeed()

        # scrapes_dict_item_ok
        request = self.conman.from_method(spider.scrapes_dict_item_ok, self.results)
        request.callback(response)
        self.should_succeed()

        # scrapes_item_fail
        request = self.conman.from_method(spider.scrapes_item_fail,
                self.results)
        request.callback(response)
        self.should_fail()

        # scrapes_dict_item_fail
        request = self.conman.from_method(spider.scrapes_dict_item_fail,
                self.results)
        request.callback(response)
        self.should_fail()

    def test_ignore_a_single_error_ok(self):
        spider = TestSpider()

        # ignore TimeoutError AND a TimeoutError is raised => SUCCESS
        request = self.conman.from_method(spider.ignore_timeout_error, self.results)
        failure = Failure(TimeoutError(), TimeoutError)
        request.errback(failure)
        self.should_succeed()

    def test_ignore_a_single_error_ko(self):
        spider = TestSpider()
        response = ResponseMock()

        # ignore TimeoutError BUT an HttpError is raised => ERROR
        request = self.conman.from_method(spider.ignore_timeout_error, self.results)
        failure = Failure(HttpError(response), HttpError)
        request.errback(failure)
        self.should_error()

    def test_ignore_multiple_errors_ok(self):
        spider = TestSpider()
        response = ResponseMock()

        # ignore TimeoutError and HttpError AND an HttpError is raised => SUCCESS
        request = self.conman.from_method(spider.ignore_timeout_and_http_errors, self.results)
        failure = Failure(HttpError(response), HttpError)
        request.errback(failure)
        self.should_succeed()

    def test_ignore_multiple_errors_ko(self):
        spider = TestSpider()

        # ignore TimeoutError and HttpError BUT a CancelledError is raised => SUCCESS
        request = self.conman.from_method(spider.ignore_timeout_and_http_errors, self.results)
        failure = Failure(CancelledError(), CancelledError)
        request.errback(failure)
        self.should_error()