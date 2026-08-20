from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest import TextTestResult

import pytest
from twisted.python import failure

from scrapy.contracts import Contract, ContractsManager
from scrapy.contracts.default import (
    CallbackKeywordArgumentsContract,
    MetadataContract,
    ReturnsContract,
    ScrapesContract,
    UrlContract,
)
from scrapy.http import Request, Response
from scrapy.item import Field, Item
from scrapy.spidermiddlewares.httperror import HttpError
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.utils.decorators import inline_callbacks_test

if TYPE_CHECKING:
    from unittest import TestResult

    from scrapy.http.request import CallbackT


def _request(
    conman: ContractsManager, method: CallbackT, results: TestResult
) -> Request:
    requests = conman.from_method(method, results)
    assert len(requests) == 1
    return requests[0]


def _call(request: Request, response: Any) -> Any:
    assert request.callback
    return request.callback(response, **request.cb_kwargs)


class DemoItem(Item):
    name = Field()
    url = Field()


class ResponseMock:
    url = "http://scrapy.org"


class ResponseMetaMock(ResponseMock):
    meta: Any = None


class TaggedRequest(Request):
    def __init__(self, url, contract_tag=None, **kwargs):
        super().__init__(url, **kwargs)
        self.contract_tag = contract_tag


class CustomSuccessContract(Contract):
    name = "custom_success_contract"

    def adjust_request_args(self, args):
        args["url"] = "http://scrapy.org"
        return args


class CustomFailContract(Contract):
    name = "custom_fail_contract"

    def adjust_request_args(self, args):
        raise TypeError("Error in adjust_request_args")


class CustomTaggedRequestContract(Contract):
    name = "custom_tagged_request"
    request_cls = TaggedRequest

    def adjust_request_args(self, args):
        args["contract_tag"] = "custom"
        args["method"] = "POST"
        return args


class DemoSpider(Spider):
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
        return DemoItem(url=response.url)

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
        return DemoItem(name=name, url=response.url)

    def returns_item_cb_kwargs_error_unexpected_keyword(self, response):
        """method which returns item
        @url http://scrapy.org
        @cb_kwargs {"arg": "value"}
        @returns items 1 1
        """
        return DemoItem(url=response.url)

    def returns_item_cb_kwargs_error_missing_argument(self, response, arg):
        """method which returns item
        @url http://scrapy.org
        @returns items 1 1
        """
        return DemoItem(url=response.url)

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
        return DemoItem(url=response.url)

    def returns_request_range_fail(self, response):
        """method which returns fewer requests than the expected range
        @url http://scrapy.org
        @returns requests 2 3
        """
        return Request("http://scrapy.org", callback=self.returns_item)

    def yields_item_and_request(self, response):
        """yields one item and one request
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        yield DemoItem(name="test", url=response.url)
        yield Request("http://scrapy.org", callback=self.returns_item)

    async def returns_async_gen(self, response):
        """async generator callback
        @url http://scrapy.org
        @returns items 1 1
        """
        yield DemoItem(url=response.url)

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
        return DemoItem(name="test", url=response.url)

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
        return DemoItem(url=response.url)

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

    def custom_tagged_request(self, response):
        """
        @url http://scrapy.org
        @custom_tagged_request
        """

    def invalid_regex(self, response):
        """method with invalid regex
        @ Scrapy is awsome
        """

    def invalid_regex_with_valid_contract(self, response):
        """method with invalid regex
        @ scrapy is awsome
        @url http://scrapy.org
        """

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
        return DemoItem(name="example", url=response.url)

    def returns_error_missing_meta(self, response):
        """method which depends of metadata be defined

        @url http://scrapy.org
        @returns items 1
        """
        key = response.meta["key"]
        yield {key: "value"}

    def returns_multiple_urls(self, response):
        """checked against two sample urls in one batch, and once more in a
        second batch, each batch with its own expectations
        @url http://scrapy.org
        @url http://example.com
        @returns items 1 1

        @url http://scrapy.org
        @returns items 0 0
        """
        return DemoItem(url=response.url)


class CustomContractSuccessSpider(Spider):
    name = "custom_contract_success_spider"

    def parse(self, response):
        """
        @custom_success_contract
        """


class CustomContractFailSpider(Spider):
    name = "custom_contract_fail_spider"

    def parse(self, response):
        """
        @custom_fail_contract
        """


class InheritsDemoSpider(DemoSpider):
    name = "inherits_demo_spider"


class TestContractsManager:
    contracts = [
        UrlContract,
        CallbackKeywordArgumentsContract,
        MetadataContract,
        ReturnsContract,
        ScrapesContract,
        CustomTaggedRequestContract,
        CustomSuccessContract,
        CustomFailContract,
    ]

    def setup_method(self):
        self.conman = ContractsManager(self.contracts)
        self.results = TextTestResult(  # type: ignore[type-var]
            stream=None, descriptions=False, verbosity=0
        )

    def should_succeed(self) -> None:
        assert not self.results.failures
        assert not self.results.errors

    def should_fail(self) -> None:
        assert self.results.failures
        assert not self.results.errors

    def should_error(self) -> None:
        assert self.results.errors

    def test_contracts(self):
        spider = DemoSpider()

        # extract contracts correctly, as a single batch
        batches = self.conman.extract_contracts(spider.returns_request)
        assert len(batches) == 1
        assert len(batches[0]) == 2
        assert frozenset(type(x) for x in batches[0]) == frozenset(
            [UrlContract, ReturnsContract]
        )

        # returns a request for a valid method
        assert len(self.conman.from_method(spider.returns_request, self.results)) == 1

        # no request for missing url
        assert self.conman.from_method(spider.parse_no_url, self.results) == []

    def test_cb_kwargs(self):
        spider = DemoSpider()
        response = ResponseMock()

        # extract contracts correctly
        (contracts,) = self.conman.extract_contracts(spider.returns_request_cb_kwargs)
        assert len(contracts) == 3
        assert frozenset(type(x) for x in contracts) == frozenset(
            [UrlContract, CallbackKeywordArgumentsContract, ReturnsContract]
        )

        (contracts,) = self.conman.extract_contracts(spider.returns_item_cb_kwargs)
        assert len(contracts) == 3
        assert frozenset(type(x) for x in contracts) == frozenset(
            [UrlContract, CallbackKeywordArgumentsContract, ReturnsContract]
        )

        (contracts,) = self.conman.extract_contracts(
            spider.returns_item_cb_kwargs_error_unexpected_keyword
        )
        assert len(contracts) == 3
        assert frozenset(type(x) for x in contracts) == frozenset(
            [UrlContract, CallbackKeywordArgumentsContract, ReturnsContract]
        )

        (contracts,) = self.conman.extract_contracts(
            spider.returns_item_cb_kwargs_error_missing_argument
        )
        assert len(contracts) == 2
        assert frozenset(type(x) for x in contracts) == frozenset(
            [UrlContract, ReturnsContract]
        )

        # returns_request
        request = _request(self.conman, spider.returns_request_cb_kwargs, self.results)
        _call(request, response)
        self.should_succeed()

        # returns_item
        request = _request(self.conman, spider.returns_item_cb_kwargs, self.results)
        _call(request, response)
        self.should_succeed()

        # returns_item (error, callback doesn't take keyword arguments)
        request = _request(
            self.conman,
            spider.returns_item_cb_kwargs_error_unexpected_keyword,
            self.results,
        )
        _call(request, response)
        self.should_error()

        # returns_item (error, contract doesn't provide keyword arguments)
        request = _request(
            self.conman,
            spider.returns_item_cb_kwargs_error_missing_argument,
            self.results,
        )
        _call(request, response)
        self.should_error()

    def test_meta(self):
        spider = DemoSpider()

        # extract contracts correctly
        (contracts,) = self.conman.extract_contracts(spider.returns_request_meta)
        assert len(contracts) == 3
        assert frozenset(type(x) for x in contracts) == frozenset(
            [UrlContract, MetadataContract, ReturnsContract]
        )

        (contracts,) = self.conman.extract_contracts(spider.returns_item_meta)
        assert len(contracts) == 3
        assert frozenset(type(x) for x in contracts) == frozenset(
            [UrlContract, MetadataContract, ReturnsContract]
        )

        response = ResponseMetaMock()

        # returns_request
        request = _request(self.conman, spider.returns_request_meta, self.results)
        assert request.meta["cookiejar"] == "session1"
        response.meta = request.meta
        _call(request, response)
        assert response.meta["cookiejar"] == "session1"
        self.should_succeed()

        response = ResponseMetaMock()

        # returns_item
        request = _request(self.conman, spider.returns_item_meta, self.results)
        assert request.meta["key"] == "example"
        response.meta = request.meta
        _call(request, response)
        assert response.meta["key"] == "example"
        self.should_succeed()

        response = ResponseMetaMock()

        request = _request(self.conman, spider.returns_error_missing_meta, self.results)
        _call(request, response)
        self.should_error()

    def test_returns(self):
        spider = DemoSpider()
        response = ResponseMock()

        # returns_item
        request = _request(self.conman, spider.returns_item, self.results)
        _call(request, response)
        self.should_succeed()

        # returns_dict_item
        request = _request(self.conman, spider.returns_dict_item, self.results)
        _call(request, response)
        self.should_succeed()

        # returns_request
        request = _request(self.conman, spider.returns_request, self.results)
        _call(request, response)
        self.should_succeed()

        # returns_fail
        request = _request(self.conman, spider.returns_fail, self.results)
        _call(request, response)
        self.should_fail()

        # returns_dict_fail
        request = _request(self.conman, spider.returns_dict_fail, self.results)
        _call(request, response)
        self.should_fail()

    def test_returns_async(self):
        spider = DemoSpider()
        response = ResponseMock()

        request = _request(self.conman, spider.returns_request_async, self.results)
        _call(request, response)
        self.should_error()

    def test_returns_invalid_argument_count(self):
        spider = DemoSpider()
        with pytest.raises(ValueError, match="expected 1, 2 or 3, got 0"):
            ReturnsContract(spider.returns_item)
        with pytest.raises(ValueError, match="expected 1, 2 or 3, got 4"):
            ReturnsContract(spider.returns_item, "items", "1", "2", "3")

    def test_returns_default_bounds(self):
        spider = DemoSpider()
        contract = ReturnsContract(spider.returns_item, "items")
        assert contract.min_bound == 1
        assert contract.max_bound == float("inf")

    def test_returns_range_fail(self):
        spider = DemoSpider()
        response = ResponseMock()

        request = _request(self.conman, spider.returns_request_range_fail, self.results)
        _call(request, response)
        self.should_fail()
        assert "expected 2..3" in self.results.failures[-1][-1]

    def test_returns_and_scrapes_ignore_other_types(self):
        spider = DemoSpider()
        response = ResponseMock()

        # @returns and @scrapes only count matching output objects and skip
        # the request that is also yielded.
        request = _request(self.conman, spider.yields_item_and_request, self.results)
        _call(request, response)
        self.should_succeed()

    def test_multiple_urls_and_batches(self):
        spider = DemoSpider()

        # a blank line starts a new batch, and each batch may repeat @url
        batches = self.conman.extract_contracts(spider.returns_multiple_urls)
        assert len(batches) == 2
        assert len(batches[0]) == 3
        assert len(batches[1]) == 2

        requests = self.conman.from_method(spider.returns_multiple_urls, self.results)
        assert sorted(request.url for request in requests) == [
            "http://example.com",
            "http://scrapy.org",
            "http://scrapy.org",
        ]

        for request in requests:
            response = ResponseMock()
            response.url = request.url
            _call(request, response)

        # the first batch expects one item from each of its two urls, and
        # gets it from both; the second batch expects zero items from its
        # url, but gets one, so only that one fails
        assert len(self.results.failures) == 1
        assert not self.results.errors

    def test_testcase_str(self):
        spider = DemoSpider()
        contract = UrlContract(spider.returns_request, "http://scrapy.org")
        assert (
            str(contract.testcase_pre)
            == "[demo_spider] returns_request (@url pre-hook)"
        )

    def test_scrapes(self):
        spider = DemoSpider()
        response = ResponseMock()

        # scrapes_item_ok
        request = _request(self.conman, spider.scrapes_item_ok, self.results)
        _call(request, response)
        self.should_succeed()

        # scrapes_dict_item_ok
        request = _request(self.conman, spider.scrapes_dict_item_ok, self.results)
        _call(request, response)
        self.should_succeed()

        # scrapes_item_fail
        request = _request(self.conman, spider.scrapes_item_fail, self.results)
        _call(request, response)
        self.should_fail()

        # scrapes_dict_item_fail
        request = _request(self.conman, spider.scrapes_dict_item_fail, self.results)
        _call(request, response)
        self.should_fail()

        # scrapes_multiple_missing_fields
        request = _request(
            self.conman, spider.scrapes_multiple_missing_fields, self.results
        )
        _call(request, response)
        self.should_fail()
        message = "ContractFail: Missing fields: name, url"
        assert message in self.results.failures[-1][-1]

    def test_regex(self):
        spider = DemoSpider()
        response = ResponseMock()

        # invalid regex
        assert self.conman.from_method(spider.invalid_regex, self.results) == []

        # invalid regex with valid contract
        request = _request(
            self.conman, spider.invalid_regex_with_valid_contract, self.results
        )
        _call(request, response)
        self.should_succeed()

    def test_custom_contracts(self):
        self.conman.from_spider(CustomContractSuccessSpider(), self.results)
        self.should_succeed()

        self.conman.from_spider(CustomContractFailSpider(), self.results)
        self.should_error()

    def test_errback(self):
        spider = DemoSpider()

        try:
            raise HttpError(Response("http://scrapy.org"), "Ignoring non-200 response")
        except HttpError:
            failure_mock = failure.Failure()

        request = _request(self.conman, spider.returns_request, self.results)
        assert request.errback
        request.errback(failure_mock)

        assert not self.results.failures
        assert self.results.errors

    @inline_callbacks_test
    def test_same_url(self):
        class TestSameUrlSpider(Spider):
            name = "test_same_url"

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.visited = 0

            async def start(self_):  # pylint: disable=no-self-argument
                for item_or_request in self.conman.from_spider(self_, self.results):
                    yield item_or_request

            def parse_first(self, response):
                self.visited += 1
                return DemoItem()

            def parse_second(self, response):
                self.visited += 1
                return DemoItem()

        with MockServer() as mockserver:
            contract_doc = f"@url {mockserver.url('/status?n=200')}"

            TestSameUrlSpider.parse_first.__doc__ = contract_doc
            TestSameUrlSpider.parse_second.__doc__ = contract_doc

            crawler = get_crawler(TestSameUrlSpider)
            yield crawler.crawl()

        assert isinstance(crawler.spider, TestSameUrlSpider)
        assert crawler.spider.visited == 2

    def test_custom_tagged_request_contract(self):
        spider = DemoSpider()
        request = _request(self.conman, spider.custom_tagged_request, self.results)
        assert request.method == "POST"
        assert isinstance(request, TaggedRequest)
        assert request.contract_tag == "custom"

    def test_inherited_contracts(self):
        spider = InheritsDemoSpider()

        requests = self.conman.from_spider(spider, self.results)
        assert requests
        assert any(
            isinstance(request, TaggedRequest) for request in requests if request
        )


class CustomFailContractPreProcess(Contract):
    name = "test_contract"

    def pre_process(self, response):
        raise KeyboardInterrupt("Pre-process exception")


class CustomFailContractPostProcess(Contract):
    name = "test_contract"

    def post_process(self, response):
        raise KeyboardInterrupt("Post-process exception")


class PreProcessSuccessContract(Contract):
    name = "pre_success"

    def pre_process(self, response):
        return


class PreProcessAssertionFailContract(Contract):
    name = "pre_assertion_fail"

    def pre_process(self, response):
        raise AssertionError("pre-process assertion")


class PreProcessErrorContract(Contract):
    name = "pre_error"

    def pre_process(self, response):
        raise ValueError("pre-process error")


class PostProcessSuccessContract(Contract):
    name = "post_success"

    def post_process(self, output):
        return


class PostProcessErrorContract(Contract):
    name = "post_error"

    def post_process(self, output):
        raise ValueError("post-process error")


class TestCustomContractPrePostProcess:
    def setup_method(self):
        self.results = TextTestResult(  # type: ignore[type-var]
            stream=None, descriptions=False, verbosity=0
        )

    def test_pre_hook_keyboard_interrupt(self):
        spider = DemoSpider()
        response = ResponseMock()
        contract = CustomFailContractPreProcess(spider.returns_request)
        conman = ContractsManager([UrlContract, ReturnsContract])

        request = _request(conman, spider.returns_request, self.results)
        contract.add_pre_hook(request, self.results)
        with pytest.raises(KeyboardInterrupt, match="Pre-process exception"):
            _call(request, response)

        assert not self.results.failures
        assert not self.results.errors

    def test_post_hook_keyboard_interrupt(self):
        spider = DemoSpider()
        response = ResponseMock()
        contract = CustomFailContractPostProcess(spider.returns_request)
        conman = ContractsManager([UrlContract, ReturnsContract])

        request = _request(conman, spider.returns_request, self.results)
        contract.add_post_hook(request, self.results)
        with pytest.raises(KeyboardInterrupt, match="Post-process exception"):
            _call(request, response)

        assert not self.results.failures
        assert not self.results.errors

    def test_pre_hook_success(self):
        spider = DemoSpider()
        response = ResponseMock()
        contract = PreProcessSuccessContract(spider.returns_request)
        conman = ContractsManager([UrlContract, ReturnsContract])

        request = _request(conman, spider.returns_request, self.results)
        contract.add_pre_hook(request, self.results)
        _call(request, response)

        assert not self.results.failures
        assert not self.results.errors

    def test_pre_hook_assertion_failure(self):
        spider = DemoSpider()
        response = ResponseMock()
        contract = PreProcessAssertionFailContract(spider.returns_request)
        conman = ContractsManager([UrlContract, ReturnsContract])

        request = _request(conman, spider.returns_request, self.results)
        contract.add_pre_hook(request, self.results)
        _call(request, response)

        assert self.results.failures
        assert not self.results.errors

    def test_pre_hook_error(self):
        spider = DemoSpider()
        response = ResponseMock()
        contract = PreProcessErrorContract(spider.returns_request)
        conman = ContractsManager([UrlContract, ReturnsContract])

        request = _request(conman, spider.returns_request, self.results)
        contract.add_pre_hook(request, self.results)
        _call(request, response)

        assert self.results.errors

    def test_pre_hook_async_callback(self):
        spider = DemoSpider()
        response = ResponseMock()
        contract = PreProcessSuccessContract(spider.returns_request_async)
        request = Request("http://scrapy.org", callback=spider.returns_request_async)
        contract.add_pre_hook(request, self.results)

        with pytest.raises(TypeError, match="async callbacks"):
            _call(request, response)

    def test_pre_hook_async_generator(self):
        spider = DemoSpider()
        response = ResponseMock()
        contract = PreProcessSuccessContract(spider.returns_async_gen)
        request = Request("http://scrapy.org", callback=spider.returns_async_gen)
        contract.add_pre_hook(request, self.results)

        with pytest.raises(TypeError, match="async callbacks"):
            _call(request, response)

    def test_post_hook_async_generator(self):
        spider = DemoSpider()
        response = ResponseMock()
        contract = PostProcessSuccessContract(spider.returns_async_gen)
        request = Request("http://scrapy.org", callback=spider.returns_async_gen)
        contract.add_post_hook(request, self.results)

        with pytest.raises(TypeError, match="async callbacks"):
            _call(request, response)

    def test_post_hook_error(self):
        spider = DemoSpider()
        response = ResponseMock()
        contract = PostProcessErrorContract(spider.returns_request)
        conman = ContractsManager([UrlContract, ReturnsContract])

        request = _request(conman, spider.returns_request, self.results)
        contract.add_post_hook(request, self.results)
        _call(request, response)

        assert self.results.errors
