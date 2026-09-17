from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from scrapy import Spider
from scrapy.http import Request
from scrapy.item import Item
from scrapy.settings import Settings
from scrapy.spiderloader import get_spider_loader
from scrapy.utils.spider import (
    iter_spider_classes,
    iterate_spider_output,
    spidercls_for_request,
)

if TYPE_CHECKING:
    from scrapy.spiderloader import SpiderLoaderProtocol


class MySpider1(Spider):
    name = "myspider1"
    allowed_domains = ["example.com", "myspider1.example"]


class MySpider2(Spider):
    name = "myspider2"
    allowed_domains = ["example.com"]


@pytest.fixture
def spider_loader() -> SpiderLoaderProtocol:
    return get_spider_loader(Settings({"SPIDER_MODULES": ["tests.test_utils_spider"]}))


def test_iterate_spider_output():
    i = Item()
    r = Request("http://scrapytest.org")
    o = object()

    assert list(iterate_spider_output(i)) == [i]  # type: ignore[call-overload]
    assert list(iterate_spider_output(r)) == [r]
    assert list(iterate_spider_output(o)) == [o]
    assert list(iterate_spider_output([r, i, o])) == [r, i, o]


def test_iter_spider_classes():
    import tests.test_utils_spider  # noqa: PLW0406,PLC0415

    it = iter_spider_classes(tests.test_utils_spider)
    assert set(it) == {MySpider1, MySpider2}


class TestSpiderclsForRequest:
    def test_single_match(self, spider_loader: SpiderLoaderProtocol) -> None:
        request = Request("http://myspider1.example/")
        assert spidercls_for_request(spider_loader, request) is MySpider1

    def test_no_match(self, spider_loader: SpiderLoaderProtocol) -> None:
        request = Request("http://toscrape.com/")
        assert spidercls_for_request(spider_loader, request) is None
        assert spidercls_for_request(spider_loader, request, MySpider1) is MySpider1

    def test_multiple_matches(self, spider_loader: SpiderLoaderProtocol) -> None:
        request = Request("http://example.com/")
        assert spidercls_for_request(spider_loader, request) is None
        assert spidercls_for_request(spider_loader, request, MySpider2) is MySpider2

    def test_log_none(
        self, spider_loader: SpiderLoaderProtocol, caplog: pytest.LogCaptureFixture
    ) -> None:
        request = Request("http://toscrape.com/")
        with caplog.at_level(logging.ERROR):
            assert spidercls_for_request(spider_loader, request, log_none=True) is None
        assert "Unable to find spider that handles" in caplog.text

    def test_log_multiple(
        self, spider_loader: SpiderLoaderProtocol, caplog: pytest.LogCaptureFixture
    ) -> None:
        request = Request("http://example.com/")
        with caplog.at_level(logging.ERROR):
            assert (
                spidercls_for_request(spider_loader, request, log_multiple=True) is None
            )
        assert "More than one spider can handle" in caplog.text
        assert "myspider1, myspider2" in caplog.text
