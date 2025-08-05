from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scrapy import Spider
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.middleware import MiddlewareManager
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


class M1:
    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process(self, response, request, spider):
        pass


class M2:
    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass


class M3:
    def process(self, response, request, spider):
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
        super()._add_middleware(mw)
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


def test_deprecated_spider_arg_no_crawler_spider(crawler: Crawler) -> None:
    """Crawler is provided, but doesn't have a spider. The instance passed to the method is
    ignored and raises a warning."""
    mwman = MyMiddlewareManager(crawler=crawler)
    with (
        pytest.warns(
            ScrapyDeprecationWarning,
            match=r"Passing a spider argument to MyMiddlewareManager.open_spider\(\) is deprecated",
        ),
        pytest.raises(
            ValueError,
            match="MyMiddlewareManager needs to access self.crawler.spider but it is None",
        ),
    ):
        mwman.open_spider(DefaultSpider())


def test_deprecated_spider_arg_with_crawler(crawler: Crawler) -> None:
    """Crawler is provided and has a spider, works. The instance passed to the method is ignored,
    even if mismatched, but raises a warning."""
    mwman = MyMiddlewareManager(crawler=crawler)
    crawler.spider = crawler._create_spider("foo")
    with pytest.warns(
        ScrapyDeprecationWarning,
        match=r"Passing a spider argument to MyMiddlewareManager.open_spider\(\) is deprecated",
    ):
        mwman.open_spider(DefaultSpider())
    with pytest.warns(
        ScrapyDeprecationWarning,
        match=r"Passing a spider argument to MyMiddlewareManager.close_spider\(\) is deprecated",
    ):
        mwman.close_spider(DefaultSpider())


def test_deprecated_spider_arg_without_crawler() -> None:
    """The first instance passed to the method is used, with a warning. Mismatched ones raise an error."""
    with pytest.warns(
        ScrapyDeprecationWarning,
        match="was called without the crawler argument",
    ):
        mwman = MyMiddlewareManager()
    with pytest.warns(
        ScrapyDeprecationWarning,
        match=r"Passing a spider argument to MyMiddlewareManager.open_spider\(\) is deprecated",
    ):
        mwman.open_spider(DefaultSpider())
    with (
        pytest.warns(
            ScrapyDeprecationWarning,
            match=r"Passing a spider argument to MyMiddlewareManager.close_spider\(\) is deprecated",
        ),
        pytest.raises(RuntimeError, match="Different instances of Spider were passed"),
    ):
        mwman.close_spider(DefaultSpider())


def test_no_spider_arg_without_crawler() -> None:
    """If no crawler and no spider arg, raise an error."""
    with pytest.warns(
        ScrapyDeprecationWarning,
        match="was called without the crawler argument",
    ):
        mwman = MyMiddlewareManager()
    with pytest.raises(
        ValueError,
        match="has no known Spider instance",
    ):
        mwman.open_spider()
