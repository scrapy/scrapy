import unittest

from scrapy import Spider
from scrapy.http import Request
from scrapy.item import BaseItem
from scrapy.utils.spider import iterate_spider_output, iter_spider_classes


class MySpider1(Spider):
    name = 'myspider1'


class MySpider2(Spider):
    name = 'myspider2'


class UtilsSpidersTestCase(unittest.TestCase):

    def test_iterate_spider_output(self):
        i = BaseItem()
        r = Request('http://scrapytest.org')
        o = object()

        self.assertEqual(list(iterate_spider_output(i)), [i])
        self.assertEqual(list(iterate_spider_output(r)), [r])
        self.assertEqual(list(iterate_spider_output(o)), [o])
        self.assertEqual(list(iterate_spider_output([r, i, o])), [r, i, o])

    def test_iter_spider_classes(self):
        import tests.test_utils_spider
        it = iter_spider_classes(tests.test_utils_spider)
        self.assertEqual(set(it), {MySpider1, MySpider2})


if __name__ == "__main__":
    unittest.main()
