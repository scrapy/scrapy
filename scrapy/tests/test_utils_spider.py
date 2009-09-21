import unittest
from scrapy.http import Request
from scrapy.item import BaseItem
from scrapy.utils.spider import iterate_spider_output


class UtilsSpidersTestCase(unittest.TestCase):

    def test_iterate_spider_output(self):
        i = BaseItem()
        r = Request('http://scrapytest.org')
        o = object()

        self.assertEqual(list(iterate_spider_output(i)), [i])
        self.assertEqual(list(iterate_spider_output(r)), [r])
        self.assertEqual(list(iterate_spider_output(o)), [o])
        self.assertEqual(list(iterate_spider_output([r, i, o])), [r, i, o])


if __name__ == "__main__":
    unittest.main()

