from unittest import TextTestResult

from twisted.internet import defer
from twisted.python import failure
from twisted.trial import unittest

from scrapy.crawler import CrawlerRunner
from scrapy.spidermiddlewares.httperror import HttpError
from scrapy.spiders import Spider
from scrapy.http import Request
from scrapy.item import Item, Field
from scrapy.contracts import ContractsManager
from scrapy.contracts.default import (
    UrlContract,
    ReturnsContract,
    ScrapesContract,
)
from tests.mockserver import MockServer


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


class InheritsTestSpider(TestSpider):
    name = 'inherits_demo_spider'


class ContractsManagerTest(unittest.TestCase):
    contracts = [UrlContract, ReturnsContract, ScrapesContract]

    def setUp(self):
        self.conman = ContractsManager(self.contracts)
        self.results = TextTestResult(stream=None, descriptions=False, verbosity=0)

    def should_succeed(self):
        self.assertFalse(self.results.failures)
        self.assertFalse(self.results.errors)

    def should_fail(self):
        self.assertTrue(self.results.failures)
        self.assertFalse(self.results.errors)

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
        request = self.conman.from_method(spider.scrapes_item_fail, self.results)
        request.callback(response)
        self.should_fail()

        # scrapes_dict_item_fail
        request = self.conman.from_method(spider.scrapes_dict_item_fail, self.results)
        request.callback(response)
        self.should_fail()

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
            mock_endpoint = mockserver.url('/status?n=200')
            TestSameUrlSpider.parse_first.__func__.__doc__ = '@url {}'.format(mock_endpoint)
            TestSameUrlSpider.parse_second.__func__.__doc__ = '@url {}'.format(mock_endpoint)

            crawler = CrawlerRunner().create_crawler(TestSameUrlSpider)
            yield crawler.crawl()

        self.assertEqual(crawler.spider.visited, 2)

    def test_inherited_contracts(self):
        spider = InheritsTestSpider()

        requests = self.conman.from_spider(spider, self.results)
        self.assertTrue(requests)
