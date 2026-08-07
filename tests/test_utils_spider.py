from __future__ import annotations

from scrapy import Spider
from scrapy.http import Request
from scrapy.item import Item
from scrapy.spiders import ignore_spider
from scrapy.utils.spider import iter_spider_classes, iterate_spider_output


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


class SpiderA2(SpiderA):
    pass


class SpiderB1(SpiderB):
    name = "b1"


class SpiderB2(SpiderB):
    pass


class SpiderC1(SpiderC):
    name = "c1"


class SpiderC2(SpiderC):
    pass


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
