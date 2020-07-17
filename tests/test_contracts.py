from unittest import TextTestResult

from twisted.internet import defer
from twisted.python import failure
from twisted.trial import unittest

from scrapy import FormRequest
from scrapy.crawler import CrawlerRunner
from scrapy.spidermiddlewares.httperror import HttpError
from scrapy.spiders import Spider
from scrapy.http import Request
from scrapy.item import Item, Field
from scrapy.contracts import ContractsManager, Contract
from scrapy.contracts.default import (
    UrlContract,
    CallbackKeywordArgumentsContract,
    ReturnsContract,
    ScrapesContract,
)
from tests.mockserver import MockServer


class TestItem(Item):
    name = Field()
    url = Field()


class ResponseMock:
    url = 'http://scrapy.org'


class CustomSuccessContract(Contract):
    name = 'custom_success_contract'

    def adjust_request_args(self, args):
        args['url'] = 'http://scrapy.org'
        return args


class CustomFailContract(Contract):
    name = 'custom_fail_contract'

    def adjust_request_args(self, args):
        raise TypeError('Error in adjust_request_args')


class CustomFormContract(Contract):
    name = 'custom_form'
    request_cls = FormRequest

    def adjust_request_args(self, args):
        args['formdata'] = {'name': 'scrapy'}
        return args


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

    def returns_request_cb_kwargs(self, response, url):
        """ method which returns request
        @url https://example.org
        @cb_kwargs {"url": "http://scrapy.org"}
        @returns requests 1
        """
        return Request(url, callback=self.returns_item_cb_kwargs)

    def returns_item_cb_kwargs(self, response, name):
        """ method which returns item
        @url http://scrapy.org
        @cb_kwargs {"name": "Scrapy"}
        @returns items 1 1
        """
        return TestItem(name=name, url=response.url)

    def returns_item_cb_kwargs_error_unexpected_keyword(self, response):
        """ method which returns item
        @url http://scrapy.org
        @cb_kwargs {"arg": "value"}
        @returns items 1 1
        """
        return TestItem(url=response.url)

    def returns_item_cb_kwargs_error_missing_argument(self, response, arg):
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

    def scrapes_multiple_missing_fields(self, response):
        """ returns item with no name
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        return {}

    def parse_no_url(self, response):
        """ method with no url
        @returns items 1 1
        """
        pass

    def custom_form(self, response):
        """
        @url http://scrapy.org
        @custom_form
        """
        pass


class CustomContractSuccessSpider(Spider):
    name = 'custom_contract_success_spider'

    def parse(self, response):
        """
        @custom_success_contract
        """
        pass


class CustomContractFailSpider(Spider):
    name = 'custom_contract_fail_spider'

    def parse(self, response):
        """
        @custom_fail_contract
        """
        pass


class InheritsTestSpider(TestSpider):
    name = 'inherits_demo_spider'


class ContractsManagerTest(unittest.TestCase):
    contracts = [
        UrlContract,
        CallbackKeywordArgumentsContract,
        ReturnsContract,
        ScrapesContract,
        CustomFormContract,
        CustomSuccessContract,
        CustomFailContract,
    ]

    def setUp(self):
        self.conman = ContractsManager(self.contracts)
        self.results = TextTestResult(stream=None, descriptions=False, verbosity=0)

    def should_succeed(self):
        self.assertFalse(self.results.failures)
        self.assertFalse(self.results.errors)

    def should_fail(self):
        self.assertTrue(self.results.failures)
        self.assertFalse(self.results.errors)

    def should_error(self):
        self.assertTrue(self.results.errors)

    def test_contracts(self):
        spider = TestSpider()

        # extract contracts correctly
        contracts = self.conman.extract_contracts(spider.returns_request)
        self.assertEqual(len(contracts), 2)
        self.assertEqual(
            frozenset(type(x) for x in contracts),
            frozenset([UrlContract, ReturnsContract]))

        # returns request for valid method
        request = self.conman.from_method(spider.returns_request, self.results)
        self.assertNotEqual(request, None)

        # no request for missing url
        request = self.conman.from_method(spider.parse_no_url, self.results)
        self.assertEqual(request, None)

    def test_cb_kwargs(self):
        spider = TestSpider()
        response = ResponseMock()

        # extract contracts correctly
        contracts = self.conman.extract_contracts(spider.returns_request_cb_kwargs)
        self.assertEqual(len(contracts), 3)
        self.assertEqual(frozenset(type(x) for x in contracts),
                         frozenset([UrlContract, CallbackKeywordArgumentsContract, ReturnsContract]))

        contracts = self.conman.extract_contracts(spider.returns_item_cb_kwargs)
        self.assertEqual(len(contracts), 3)
        self.assertEqual(frozenset(type(x) for x in contracts),
                         frozenset([UrlContract, CallbackKeywordArgumentsContract, ReturnsContract]))

        contracts = self.conman.extract_contracts(spider.returns_item_cb_kwargs_error_unexpected_keyword)
        self.assertEqual(len(contracts), 3)
        self.assertEqual(frozenset(type(x) for x in contracts),
                         frozenset([UrlContract, CallbackKeywordArgumentsContract, ReturnsContract]))

        contracts = self.conman.extract_contracts(spider.returns_item_cb_kwargs_error_missing_argument)
        self.assertEqual(len(contracts), 2)
        self.assertEqual(frozenset(type(x) for x in contracts),
                         frozenset([UrlContract, ReturnsContract]))

        # returns_request
        request = self.conman.from_method(spider.returns_request_cb_kwargs, self.results)
        request.callback(response, **request.cb_kwargs)
        self.should_succeed()

        # returns_item
        request = self.conman.from_method(spider.returns_item_cb_kwargs, self.results)
        request.callback(response, **request.cb_kwargs)
        self.should_succeed()

        # returns_item (error, callback doesn't take keyword arguments)
        request = self.conman.from_method(spider.returns_item_cb_kwargs_error_unexpected_keyword, self.results)
        request.callback(response, **request.cb_kwargs)
        self.should_error()

        # returns_item (error, contract doesn't provide keyword arguments)
        request = self.conman.from_method(spider.returns_item_cb_kwargs_error_missing_argument, self.results)
        request.callback(response, **request.cb_kwargs)
        self.should_error()

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
        request = self.conman.from_method(spider.scrapes_item_fail, self.results)
        request.callback(response)
        self.should_fail()

        # scrapes_dict_item_fail
        request = self.conman.from_method(spider.scrapes_dict_item_fail, self.results)
        request.callback(response)
        self.should_fail()

        # scrapes_multiple_missing_fields
        request = self.conman.from_method(spider.scrapes_multiple_missing_fields, self.results)
        request.callback(response)
        self.should_fail()
        message = 'ContractFail: Missing fields: name, url'
        assert message in self.results.failures[-1][-1]

    def test_custom_contracts(self):
        self.conman.from_spider(CustomContractSuccessSpider(), self.results)
        self.should_succeed()

        self.conman.from_spider(CustomContractFailSpider(), self.results)
        self.should_error()

    def test_errback(self):
        spider = TestSpider()
        response = ResponseMock()

        try:
            raise HttpError(response, 'Ignoring non-200 response')
        except HttpError:
            failure_mock = failure.Failure()

        request = self.conman.from_method(spider.returns_request, self.results)
        request.errback(failure_mock)

        self.assertFalse(self.results.failures)
        self.assertTrue(self.results.errors)

    @defer.inlineCallbacks
    def test_same_url(self):

        class TestSameUrlSpider(Spider):
            name = 'test_same_url'

            def __init__(self, *args, **kwargs):
                super(TestSameUrlSpider, self).__init__(*args, **kwargs)
                self.visited = 0

            def start_requests(s):
                return self.conman.from_spider(s, self.results)

            def parse_first(self, response):
                self.visited += 1
                return TestItem()

            def parse_second(self, response):
                self.visited += 1
                return TestItem()

        with MockServer() as mockserver:
            contract_doc = '@url {}'.format(mockserver.url('/status?n=200'))

            TestSameUrlSpider.parse_first.__doc__ = contract_doc
            TestSameUrlSpider.parse_second.__doc__ = contract_doc

            crawler = CrawlerRunner().create_crawler(TestSameUrlSpider)
            yield crawler.crawl()

        self.assertEqual(crawler.spider.visited, 2)

    def test_form_contract(self):
        spider = TestSpider()
        request = self.conman.from_method(spider.custom_form, self.results)
        self.assertEqual(request.method, 'POST')
        self.assertIsInstance(request, FormRequest)

    def test_inherited_contracts(self):
        spider = InheritsTestSpider()

        requests = self.conman.from_spider(spider, self.results)
        self.assertTrue(requests)
