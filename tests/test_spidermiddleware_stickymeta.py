from unittest import TestCase

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.http import Request, Response
from scrapy.item import Field, Item
from scrapy.spidermiddlewares.stickymeta import StickyMetaParamsMiddleware
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


class MockItem(Item):
    name = Field()


class TestStickyMetaParamsMiddleware(TestCase):

    def setUp(self):
        self.test_url = 'http://www.example.com'

    def create_middleware(self, crawler):
        return StickyMetaParamsMiddleware.from_crawler(crawler)

    def test_middleware_not_enabled(self):
        crawler = get_crawler(Spider)
        with pytest.raises(NotConfigured):
            self.create_middleware(crawler)

    def test_sticky_params(self):
        crawler = get_crawler(Spider, {'STICKY_META_KEYS': ['param2']})
        middleware = self.create_middleware(crawler)
        request = Request(
            self.test_url,
            meta={
                'param': 'Will not be stickied',
                'param2': 'Stickied!'
            })
        response = Response(self.test_url, request=request)
        result = [
            Request(self.test_url),
            MockItem(name='dummy')
        ]
        results = middleware.process_spider_output(response, result, None)
        for result in results:
            if isinstance(result, Request):
                self.assertEqual(result.meta, {'param2': 'Stickied!'})

    def test_comma_separated_string_setting(self):
        crawler = get_crawler(Spider, {'STICKY_META_KEYS': 'param1,param2'})
        middleware = self.create_middleware(crawler)
        assert type(middleware.keys_to_sticky) is list
        assert middleware.keys_to_sticky == ['param1', 'param2']

    def test_sticky_param_does_not_override_manually_configured_param(self):
        crawler = get_crawler(
            Spider,
            {'STICKY_META_KEYS': ['param', 'param2']}
        )
        middleware = self.create_middleware(crawler)
        request = Request(
            self.test_url,
            meta={
                'param': 'Stickied!',
                'param2': 'Stickied!'
            })
        response = Response(self.test_url, request=request)
        result = [
            Request(self.test_url, meta={'param': 'Override stickied'}),
            MockItem(name='dummy')
        ]
        results = middleware.process_spider_output(response, result, None)
        for result in results:
            if isinstance(result, Request):
                self.assertEqual(
                    result.meta,
                    {
                        'param': 'Override stickied',
                        'param2': 'Stickied!'
                    }
                )
