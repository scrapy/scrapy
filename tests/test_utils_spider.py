from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from scrapy import Spider
from scrapy.http import Request
from scrapy.item import Item
from scrapy.settings import Settings
from scrapy.spiderloader import get_spider_loader
from scrapy.spiders import ignore_spider
from scrapy.utils.spider import (
    iter_spider_classes,
    iterate_spider_output,
    spidercls_for_request,
)

if TYPE_CHECKING:
    from scrapy.spiderloader import SpiderLoaderProtocol


class SpiderA(Spider):
    pass


@ignore_spider
class SpiderB(Spider):
    pass


@ignore_spider
class SpiderC(Spider):
    name = "c"


class SpiderA1(SpiderA):
    name = "a1"
    allowed_domains = ["example.com", "a1.example"]


class SpiderA2(SpiderA):
    pass


class SpiderB1(SpiderB):
    name = "b1"
    allowed_domains = ["example.com"]


class SpiderB2(SpiderB):
    pass


class SpiderC1(SpiderC):
    name = "c1"


class SpiderC2(SpiderC):
    pass


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


def test_iter_spider_classes_require_name():
    import tests.test_utils_spider  # noqa: PLW0406,PLC0415

    it = iter_spider_classes(tests.test_utils_spider, require_name=True)
    assert set(it) == {SpiderA1, SpiderB1, SpiderC1, SpiderC2}


def test_iter_spider_classes_dont_require_name():
    import tests.test_utils_spider  # noqa: PLW0406,PLC0415

    it = iter_spider_classes(tests.test_utils_spider, require_name=False)
    assert set(it) == {
        SpiderA,
        SpiderA1,
        SpiderA2,
        SpiderB1,
        SpiderB2,
        SpiderC1,
        SpiderC2,
    }


class TestSpiderclsForRequest:
    def test_single_match(self, spider_loader: SpiderLoaderProtocol) -> None:
        request = Request("http://a1.example/")
        assert spidercls_for_request(spider_loader, request) is SpiderA1

    def test_no_match(self, spider_loader: SpiderLoaderProtocol) -> None:
        request = Request("http://toscrape.com/")
        assert spidercls_for_request(spider_loader, request) is None
        assert spidercls_for_request(spider_loader, request, SpiderA1) is SpiderA1

    def test_multiple_matches(self, spider_loader: SpiderLoaderProtocol) -> None:
        request = Request("http://example.com/")
        assert spidercls_for_request(spider_loader, request) is None
        assert spidercls_for_request(spider_loader, request, SpiderB1) is SpiderB1

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
        assert "a1, b1" in caplog.text
