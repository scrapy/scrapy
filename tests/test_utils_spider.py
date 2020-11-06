import unittest

from scrapy import Spider
from scrapy.http import Request
from scrapy.spiders import ignore_spider
from scrapy.item import Item
from scrapy.utils.spider import iterate_spider_output, iter_spider_classes


class SpiderA(Spider):
    pass


@ignore_spider
class SpiderB(Spider):
    pass


@ignore_spider
class SpiderC(Spider):
    name = 'c'


class SpiderA1(SpiderA):
    name = 'a1'


class SpiderA2(SpiderA):
    pass


class SpiderB1(SpiderB):
    name = 'b1'


class SpiderB2(SpiderB):
    pass


class SpiderC1(SpiderC):
    name = 'c1'


class SpiderC2(SpiderC):
    pass


class UtilsSpidersTestCase(unittest.TestCase):

    def test_iterate_spider_output(self):
        i = Item()
        r = Request('http://scrapytest.org')
        o = object()

        self.assertEqual(list(iterate_spider_output(i)), [i])
        self.assertEqual(list(iterate_spider_output(r)), [r])
        self.assertEqual(list(iterate_spider_output(o)), [o])
        self.assertEqual(list(iterate_spider_output([r, i, o])), [r, i, o])

    def test_iter_spider_classes_require_name(self):
        import tests.test_utils_spider
        it = iter_spider_classes(tests.test_utils_spider, require_name=True)
        self.assertEqual(set(it), {SpiderA1, SpiderB1, SpiderC1, SpiderC2})

    def test_iter_spider_classes_dont_require_name(self):
        import tests.test_utils_spider
        it = iter_spider_classes(tests.test_utils_spider, require_name=False)
        self.assertEqual(set(it), {SpiderA, SpiderA1, SpiderA2, SpiderB1,
                                   SpiderB2, SpiderC1, SpiderC2})


if __name__ == "__main__":
    unittest.main()
