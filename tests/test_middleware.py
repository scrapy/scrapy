from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scrapy import Spider
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.middleware import MiddlewareManager
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


class M1:
    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process(self, response, request):
        pass


class M2:
    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass


class M3:
    def process(self, response, request):
        pass


class MOff:
    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def __init__(self):
        raise NotConfigured("foo")


class MyMiddlewareManager(MiddlewareManager):
    component_name = "my"

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return [M1, MOff, M3]

    def _add_middleware(self, mw):
        if hasattr(mw, "open_spider"):
            self.methods["open_spider"].append(mw.open_spider)
        if hasattr(mw, "close_spider"):
            self.methods["close_spider"].appendleft(mw.close_spider)
        if hasattr(mw, "process"):
            self.methods["process"].append(mw.process)


@pytest.fixture
def crawler() -> Crawler:
    return get_crawler(Spider)


def test_init(crawler: Crawler) -> None:
    m1, m2, m3 = M1(), M2(), M3()
    mwman = MyMiddlewareManager(m1, m2, m3, crawler=crawler)
    assert list(mwman.methods["open_spider"]) == [m1.open_spider, m2.open_spider]
    assert list(mwman.methods["close_spider"]) == [m2.close_spider, m1.close_spider]
    assert list(mwman.methods["process"]) == [m1.process, m3.process]
    assert mwman.crawler == crawler


def test_methods(crawler: Crawler) -> None:
    mwman = MyMiddlewareManager(M1(), M2(), M3(), crawler=crawler)
    assert [x.__self__.__class__ for x in mwman.methods["open_spider"]] == [M1, M2]  # type: ignore[union-attr]
    assert [x.__self__.__class__ for x in mwman.methods["close_spider"]] == [M2, M1]  # type: ignore[union-attr]
    assert [x.__self__.__class__ for x in mwman.methods["process"]] == [M1, M3]  # type: ignore[union-attr]


def test_enabled(crawler: Crawler) -> None:
    m1, m2, m3 = M1(), M2(), M3()
    mwman = MyMiddlewareManager(m1, m2, m3, crawler=crawler)
    assert mwman.middlewares == (m1, m2, m3)


def test_enabled_from_settings(crawler: Crawler) -> None:
    crawler = get_crawler()
    mwman = MyMiddlewareManager.from_crawler(crawler)
    classes = [x.__class__ for x in mwman.middlewares]
    assert classes == [M1, M3]
    assert mwman.crawler == crawler


def test_no_crawler() -> None:
    m1, m2, m3 = M1(), M2(), M3()
    with pytest.warns(
        ScrapyDeprecationWarning, match="was called without the crawler argument"
    ):
        mwman = MyMiddlewareManager(m1, m2, m3)
    assert mwman.middlewares == (m1, m2, m3)
    assert mwman.crawler is None
