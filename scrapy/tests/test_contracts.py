from twisted.trial import unittest

from scrapy.spider import BaseSpider
from scrapy.http import Request
from scrapy.item import Item, Field
from scrapy.exceptions import ContractFail
from scrapy.contracts import ContractsManager
from scrapy.contracts.default import (
    UrlContract,
    ReturnsContract,
    ScrapesContract,
)


class TestItem(Item):
    name = Field()
    url = Field()


class ResponseMock(object):
    url = 'http://scrapy.org'


class TestSpider(BaseSpider):
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

    def returns_fail(self, response):
        """ method which returns item
        @url http://scrapy.org
        @returns items 0 0
        """
        return TestItem(url=response.url)

    def scrapes_item_ok(self, response):
        """ returns item with name and url
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        return TestItem(name='test', url=response.url)

    def scrapes_item_fail(self, response):
        """ returns item with no name
        @url http://scrapy.org
        @returns items 1 1
        @scrapes name url
        """
        return TestItem(url=response.url)

    def parse_no_url(self, response):
        """ method with no url
        @returns items 1 1
        """
        pass


class ContractsManagerTest(unittest.TestCase):
    contracts = [UrlContract, ReturnsContract, ScrapesContract]

    def test_contracts(self):
        conman = ContractsManager(self.contracts)

        # extract contracts correctly
        contracts = conman.extract_contracts(TestSpider.returns_request)
        self.assertEqual(len(contracts), 2)
        self.assertEqual(frozenset(map(type, contracts)),
            frozenset([UrlContract, ReturnsContract]))

        # returns request for valid method
        request = conman.from_method(TestSpider.returns_request)
        self.assertNotEqual(request, None)

        # no request for missing url
        request = conman.from_method(TestSpider.parse_no_url)
        self.assertEqual(request, None)

    def test_returns(self):
        conman = ContractsManager(self.contracts)

        spider = TestSpider()
        response = ResponseMock()

        # returns_item
        request = conman.from_method(spider.returns_item, fail=True)
        output = request.callback(response)
        self.assertEqual(map(type, output), [TestItem])

        # returns_request
        request = conman.from_method(spider.returns_request, fail=True)
        output = request.callback(response)
        self.assertEqual(map(type, output), [Request])

        # returns_fail
        request = conman.from_method(spider.returns_fail, fail=True)
        self.assertRaises(ContractFail, request.callback, response)

    def test_scrapes(self):
        conman = ContractsManager(self.contracts)

        spider = TestSpider()
        response = ResponseMock()

        # scrapes_item_ok
        request = conman.from_method(spider.scrapes_item_ok, fail=True)
        output = request.callback(response)
        self.assertEqual(map(type, output), [TestItem])

        # scrapes_item_fail
        request = conman.from_method(spider.scrapes_item_fail, fail=True)
        self.assertRaises(ContractFail, request.callback, response)
