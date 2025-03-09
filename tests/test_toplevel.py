import scrapy


class TestToplevel:
    def test_version(self):
        assert isinstance(scrapy.__version__, str)

    def test_version_info(self):
        assert isinstance(scrapy.version_info, tuple)

    def test_request_shortcut(self):
        from scrapy.http import FormRequest, Request

        assert scrapy.Request is Request
        assert scrapy.FormRequest is FormRequest

    def test_spider_shortcut(self):
        from scrapy.spiders import Spider

        assert scrapy.Spider is Spider

    def test_selector_shortcut(self):
        from scrapy.selector import Selector

        assert scrapy.Selector is Selector

    def test_item_shortcut(self):
        from scrapy.item import Field, Item

        assert scrapy.Item is Item
        assert scrapy.Field is Field
