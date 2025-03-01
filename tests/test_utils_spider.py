from scrapy import Spider
from scrapy.http import Request
from scrapy.item import Item
from scrapy.utils.spider import iter_spider_classes, iterate_spider_output


class MySpider1(Spider):
    name = "myspider1"


class MySpider2(Spider):
    name = "myspider2"


class TestUtilsSpiders:
    def test_iterate_spider_output(self):
        i = Item()
        r = Request("http://scrapytest.org")
        o = object()

        assert list(iterate_spider_output(i)) == [i]
        assert list(iterate_spider_output(r)) == [r]
        assert list(iterate_spider_output(o)) == [o]
        assert list(iterate_spider_output([r, i, o])) == [r, i, o]

    def test_iter_spider_classes(self):
        import tests.test_utils_spider  # noqa: PLW0406  # pylint: disable=import-self

        it = iter_spider_classes(tests.test_utils_spider)
        assert set(it) == {MySpider1, MySpider2}
