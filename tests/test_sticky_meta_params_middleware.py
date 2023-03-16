from unittest import TestCase

import pytest
from scrapy.exceptions import NotConfigured
from scrapy.http import Request, Response
from scrapy.item import Field, Item
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler

from scrapy.spidermiddlewares.sticky_meta import StickyMetaParamsMiddleware


class MockItem(Item):
    name = Field()


class TestStickyMetaParamsMiddleware(TestCase):
    def setUp(self):
        self.test_url = "http://www.example.com"

    def create_middleware(self, crawler):
        return StickyMetaParamsMiddleware.from_crawler(crawler)

    def _get_crawler(self, spider):
        crawler = get_crawler(Spider)
        crawler.spider = spider
        return crawler

    def test_middleware_not_enabled(self):
        spider = Spider("dummy")
        crawler = self._get_crawler(spider)
        with pytest.raises(NotConfigured):
            self.create_middleware(crawler)

    def test_sticky_params(self):
        """A new request.meta must contain the previous response.meta stickied parameter"""
        spider = Spider("dummy")
        spider.sticky_meta_keys = ["param2"]
        crawler = self._get_crawler(spider)
        middleware = self.create_middleware(crawler)
        request = Request(
            self.test_url, meta={"param": "Will not be stickied", "param2": "Stickied!"}
        )
        response = Response(self.test_url, request=request)
        result = [
            Request(self.test_url),
            MockItem(name="dummy"),  # Add a item just to increase the test coverage
        ]
        for result in middleware.process_spider_output(response, result, spider):
            if isinstance(result, Request):
                self.assertEqual(result.meta, {"param2": "Stickied!"})

    def test_replace_sticky_params(self):
        """A stickied parameter should be overriten if the sticked parameter was set in the new request"""
        spider = Spider("dummy")
        spider.sticky_meta_keys = ["param2"]
        crawler = self._get_crawler(spider)
        middleware = self.create_middleware(crawler)
        request = Request(self.test_url, meta={"param2": "Stickied!"})
        response = Response(self.test_url, request=request)
        result = [
            Request(self.test_url, meta={"param2": "Replaced"}),
            MockItem(name="dummy"),  # Add a item just to increase the test coverage
        ]
        for result in middleware.process_spider_output(response, result, spider):
            if isinstance(result, Request):
                self.assertEqual(result.meta, {"param2": "Replaced"})
