from unittest import TextTestResult

from twisted.internet import defer
from twisted.python import failure
from twisted.trial import unittest

from scrapy import FormRequest
from scrapy.contracts import Contract, ContractsManager
from scrapy.contracts.default import (
    CallbackKeywordArgumentsContract,
    MetadataContract,
    ReturnsContract,
    ScrapesContract,
    UrlContract,
)
from scrapy.http import Request
from scrapy.item import Field, Item
from scrapy.spidermiddlewares.httperror import HttpError
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer


class TestItem(Item):
    name = Field()
    url = Field()


class ResponseMock:
    url = "http://scrapy.org"


class ResponseMetaMock(ResponseMock):
    meta = None


class CustomSuccessContract(Contract):
    name = "custom_success_contract"

    def adjust_request_args(self, args):
        args["url"] = "http://scrapy.org"
        return args


class CustomFailContract(Contract):
    name = "custom_fail_contract"

    def adjust_request_args(self, args):
        raise TypeError("Error in adjust_request_args")


class CustomFormContract(Contract):
    name = "custom_form"
    request_cls = FormRequest

    def adjust_request_args(self, args):
        args["formdata"] = {"name": "scrapy"}
        return args


class TestSpider(Spider):
    name = "demo_spider"

    def returns_request(self, response):
        """method which returns request
        @url http://scrapy.org
        @returns requests 1
        """
        return Request("http://scrapy.org", callback=self.returns_item)

    async def returns_request_async(self, response):
        """async method which returns request
        @url http://scrapy.org
        @returns requests 1
        """
        return Request("http://scrapy.org", callback=self.returns_item)

    def returns_item(self, response):
        """method which returns item
        @url http://scrapy.org
        @returns items 1 1
        """
        return TestItem(url=response.url)

    def returns_request_cb_kwargs(self, response, url):
        """method which returns request
        @url https://example.org
        @cb_kwargs {"url": "http://scrapy.org"}
        @returns requests 1
        """
        return Request(url, callback=self.returns_item_cb_kwargs)

    def returns_item_cb_kwargs(self, response, name):
        """method which returns item
        @url http://scrapy.org
        @cb_kwargs {"name": "Scrapy"}
        @returns items 1 1
        """
        return TestItem(name=name, url=response.url)

    def returns_item_cb_kwargs_error_unexpected_keyword(self, response):
        """method which returns item
        @url http://scrapy.org
        @cb_kwargs {"arg": "value"}
        @returns items 1 1
        """
        return TestItem(url=response.url)

    def returns_item_cb_kwargs_error_missing_argument(self, response, arg):
        """method which returns item
        @url http://scrapy.org
        @returns items 1 1
        """
        return TestItem(url=response.url)

    def returns_dict_item(self, response):
        """method which returns item
        @url http://scrapy.org
        @returns items 1 1
        """
        return {"url": response.url}

    def returns_fail(self, response):
        """method which returns item
        @url http://scrapy.org
        @returns items 0 0
        """
        return TestItem(url=response.url)

    def returns_dict_fail(self, response):
        """method which returns item
        @url http://scrapy.org
        @returns items 0 0
        """
        return {"url": response.url}

    def scrapes_item_ok(self, response):
        """returns item with name and url
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        return TestItem(name="test", url=response.url)

    def scrapes_dict_item_ok(self, response):
        """returns item with name and url
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        return {"name": "test", "url": response.url}

    def scrapes_item_fail(self, response):
        """returns item with no name
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        return TestItem(url=response.url)

    def scrapes_dict_item_fail(self, response):
        """returns item with no name
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        return {"url": response.url}

    def scrapes_multiple_missing_fields(self, response):
        """returns item with no name
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        return {}

    def parse_no_url(self, response):
        """method with no url
        @returns items 1 1
        """
        pass

    def custom_form(self, response):
        """
        @url http://scrapy.org
        @custom_form
        """
        pass

    def invalid_regex(self, response):
        """method with invalid regex
        @ Scrapy is awsome
        """
        pass

    def invalid_regex_with_valid_contract(self, response):
        """method with invalid regex
        @ scrapy is awsome
        @url http://scrapy.org
        """
        pass

    def returns_request_meta(self, response):
        """method which returns request
        @url https://example.org
        @meta {"cookiejar": "session1"}
        @returns requests 1
        """
        return Request(
            "https://example.org", meta=response.meta, callback=self.returns_item_meta
        )

    def returns_item_meta(self, response):
        """method which returns item
        @url http://scrapy.org
        @meta {"key": "example"}
        @returns items 1 1
        """
        return TestItem(name="example", url=response.url)

    def returns_error_missing_meta(self, response):
        """method which depends of metadata be defined

        @url http://scrapy.org
        @returns items 1
        """
        key = response.meta["key"]
        yield {key: "value"}


class CustomContractSuccessSpider(Spider):
    name = "custom_contract_success_spider"

    def parse(self, response):
        """
        @custom_success_contract
        """
        pass


class CustomContractFailSpider(Spider):
    name = "custom_contract_fail_spider"

    def parse(self, response):
        """
        @custom_fail_contract
        """
        pass


class InheritsTestSpider(TestSpider):
    name = "inherits_demo_spider"


class ContractsManagerTest(unittest.TestCase):
    contracts = [
        UrlContract,
        CallbackKeywordArgumentsContract,
        MetadataContract,
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
            frozenset([UrlContract, ReturnsContract]),
        )

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
        self.assertEqual(
            frozenset(type(x) for x in contracts),
            frozenset([UrlContract, CallbackKeywordArgumentsContract, ReturnsContract]),
        )

        contracts = self.conman.extract_contracts(spider.returns_item_cb_kwargs)
        self.assertEqual(len(contracts), 3)
        self.assertEqual(
            frozenset(type(x) for x in contracts),
            frozenset([UrlContract, CallbackKeywordArgumentsContract, ReturnsContract]),
        )

        contracts = self.conman.extract_contracts(
            spider.returns_item_cb_kwargs_error_unexpected_keyword
        )
        self.assertEqual(len(contracts), 3)
        self.assertEqual(
            frozenset(type(x) for x in contracts),
            frozenset([UrlContract, CallbackKeywordArgumentsContract, ReturnsContract]),
        )

        contracts = self.conman.extract_contracts(
            spider.returns_item_cb_kwargs_error_missing_argument
        )
        self.assertEqual(len(contracts), 2)
        self.assertEqual(
            frozenset(type(x) for x in contracts),
            frozenset([UrlContract, ReturnsContract]),
        )

        # returns_request
        request = self.conman.from_method(
            spider.returns_request_cb_kwargs, self.results
        )
        request.callback(response, **request.cb_kwargs)
        self.should_succeed()

        # returns_item
        request = self.conman.from_method(spider.returns_item_cb_kwargs, self.results)
        request.callback(response, **request.cb_kwargs)
        self.should_succeed()

        # returns_item (error, callback doesn't take keyword arguments)
        request = self.conman.from_method(
            spider.returns_item_cb_kwargs_error_unexpected_keyword, self.results
        )
        request.callback(response, **request.cb_kwargs)
        self.should_error()

        # returns_item (error, contract doesn't provide keyword arguments)
        request = self.conman.from_method(
            spider.returns_item_cb_kwargs_error_missing_argument, self.results
        )
        request.callback(response, **request.cb_kwargs)
        self.should_error()

    def test_meta(self):
        spider = TestSpider()

        # extract contracts correctly
        contracts = self.conman.extract_contracts(spider.returns_request_meta)
        self.assertEqual(len(contracts), 3)
        self.assertEqual(
            frozenset(type(x) for x in contracts),
            frozenset([UrlContract, MetadataContract, ReturnsContract]),
        )

        contracts = self.conman.extract_contracts(spider.returns_item_meta)
        self.assertEqual(len(contracts), 3)
        self.assertEqual(
            frozenset(type(x) for x in contracts),
            frozenset([UrlContract, MetadataContract, ReturnsContract]),
        )

        response = ResponseMetaMock()

        # returns_request
        request = self.conman.from_method(spider.returns_request_meta, self.results)
        assert request.meta["cookiejar"] == "session1"
        response.meta = request.meta
        request.callback(response)
        assert response.meta["cookiejar"] == "session1"
        self.should_succeed()

        response = ResponseMetaMock()

        # returns_item
        request = self.conman.from_method(spider.returns_item_meta, self.results)
        assert request.meta["key"] == "example"
        response.meta = request.meta
        request.callback(ResponseMetaMock)
        assert response.meta["key"] == "example"
        self.should_succeed()

        response = ResponseMetaMock()

        request = self.conman.from_method(
            spider.returns_error_missing_meta, self.results
        )
        request.callback(response)
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

    def test_returns_async(self):
        spider = TestSpider()
        response = ResponseMock()

        request = self.conman.from_method(spider.returns_request_async, self.results)
        request.callback(response)
        self.should_error()

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
        request = self.conman.from_method(
            spider.scrapes_multiple_missing_fields, self.results
        )
        request.callback(response)
        self.should_fail()
        message = "ContractFail: Missing fields: name, url"
        assert message in self.results.failures[-1][-1]

    def test_regex(self):
        spider = TestSpider()
        response = ResponseMock()

        # invalid regex
        request = self.conman.from_method(spider.invalid_regex, self.results)
        self.should_succeed()

        # invalid regex with valid contract
        request = self.conman.from_method(
            spider.invalid_regex_with_valid_contract, self.results
        )
        self.should_succeed()
        request.callback(response)

    def test_custom_contracts(self):
        self.conman.from_spider(CustomContractSuccessSpider(), self.results)
        self.should_succeed()

        self.conman.from_spider(CustomContractFailSpider(), self.results)
        self.should_error()

    def test_errback(self):
        spider = TestSpider()
        response = ResponseMock()

        try:
            raise HttpError(response, "Ignoring non-200 response")
        except HttpError:
            failure_mock = failure.Failure()

        request = self.conman.from_method(spider.returns_request, self.results)
        request.errback(failure_mock)

        self.assertFalse(self.results.failures)
        self.assertTrue(self.results.errors)

    @defer.inlineCallbacks
    def test_same_url(self):
        class TestSameUrlSpider(Spider):
            name = "test_same_url"

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
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
            contract_doc = f'@url {mockserver.url("/status?n=200")}'

            TestSameUrlSpider.parse_first.__doc__ = contract_doc
            TestSameUrlSpider.parse_second.__doc__ = contract_doc

            crawler = get_crawler(TestSameUrlSpider)
            yield crawler.crawl()

        self.assertEqual(crawler.spider.visited, 2)

    def test_form_contract(self):
        spider = TestSpider()
        request = self.conman.from_method(spider.custom_form, self.results)
        self.assertEqual(request.method, "POST")
        self.assertIsInstance(request, FormRequest)

    def test_inherited_contracts(self):
        spider = InheritsTestSpider()

        requests = self.conman.from_spider(spider, self.results)
        self.assertTrue(requests)


class CustomFailContractPreProcess(Contract):
    name = "test_contract"

    def pre_process(self, response):
        raise KeyboardInterrupt("Pre-process exception")


class CustomFailContractPostProcess(Contract):
    name = "test_contract"

    def post_process(self, response):
        raise KeyboardInterrupt("Post-process exception")


class CustomContractPrePostProcess(unittest.TestCase):

    def setUp(self):
        self.results = TextTestResult(stream=None, descriptions=False, verbosity=0)

    def test_pre_hook_keyboard_interrupt(self):
        spider = TestSpider()
        response = ResponseMock()
        contract = CustomFailContractPreProcess(spider.returns_request)
        conman = ContractsManager([contract])

        try:
            request = conman.from_method(spider.returns_request, self.results)
            contract.add_pre_hook(request, self.results)
            # Expect this to raise a KeyboardInterrupt
            request.callback(response, **request.cb_kwargs)
        except KeyboardInterrupt as e:
            self.assertEqual(str(e), "Pre-process exception")
        else:
            self.fail("KeyboardInterrupt not raised")

        self.assertFalse(self.results.failures)
        self.assertFalse(self.results.errors)

    def test_post_hook_keyboard_interrupt(self):
        spider = TestSpider()
        response = ResponseMock()
        contract = CustomFailContractPostProcess(spider.returns_request)
        conman = ContractsManager([contract])

        try:
            request = conman.from_method(spider.returns_request, self.results)
            contract.add_post_hook(request, self.results)
            # Expect this to raise a KeyboardInterrupt
            request.callback(response, **request.cb_kwargs)
        except KeyboardInterrupt as e:
            self.assertEqual(str(e), "Post-process exception")
        else:
            self.fail("KeyboardInterrupt not raised")

        self.assertFalse(self.results.failures)
        self.assertFalse(self.results.errors)
