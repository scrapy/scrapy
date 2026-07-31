import scrapy


def test_version():
    assert isinstance(scrapy.__version__, str)


def test_version_info():
    assert isinstance(scrapy.version_info, tuple)


def test_request_shortcut():
    from scrapy.http import FormRequest, Request  # noqa: PLC0415

    assert scrapy.Request is Request
    assert scrapy.FormRequest is FormRequest


def test_spider_shortcut():
    from scrapy.spiders import Spider  # noqa: PLC0415

    assert scrapy.Spider is Spider


def test_selector_shortcut():
    from scrapy.selector import Selector  # noqa: PLC0415

    assert scrapy.Selector is Selector


def test_item_shortcut():
    from scrapy.item import Field, Item  # noqa: PLC0415

    assert scrapy.Item is Item
    assert scrapy.Field is Field
