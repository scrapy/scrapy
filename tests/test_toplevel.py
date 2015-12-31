from unittest import TestCase
import six
import scrapy


class ToplevelTestCase(TestCase):

    def test_version(self):
        self.assertIs(type(scrapy.__version__), six.text_type)

    def test_version_info(self):
        self.assertIs(type(scrapy.version_info), tuple)

    def test_request_shortcut(self):
        from scrapy.http import Request, FormRequest
        self.assertIs(scrapy.Request, Request)
        self.assertIs(scrapy.FormRequest, FormRequest)

    def test_spider_shortcut(self):
        from scrapy.spiders import Spider
        self.assertIs(scrapy.Spider, Spider)

    def test_selector_shortcut(self):
        from scrapy.selector import Selector
        self.assertIs(scrapy.Selector, Selector)

    def test_item_shortcut(self):
        from scrapy.item import Item, Field
        self.assertIs(scrapy.Item, Item)
        self.assertIs(scrapy.Field, Field)
