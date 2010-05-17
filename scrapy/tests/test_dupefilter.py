import unittest

from scrapy.http import Request
from scrapy.spider import BaseSpider
from scrapy.contrib.dupefilter import RequestFingerprintDupeFilter, NullDupeFilter


class RequestFingerprintDupeFilterTest(unittest.TestCase):

    def test_filter(self):
        spider = BaseSpider('foo')
        filter = RequestFingerprintDupeFilter()
        filter.open_spider(spider)

        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')

        assert not filter.request_seen(spider, r1)
        assert filter.request_seen(spider, r1)

        assert not filter.request_seen(spider, r2)
        assert filter.request_seen(spider, r3)

        filter.close_spider(spider)


class NullDupeFilterTest(unittest.TestCase):

    def test_filter(self):
        spider = BaseSpider('foo')
        filter = NullDupeFilter()
        filter.open_spider(spider)

        r1 = Request('http://scrapytest.org/1')
        assert not filter.request_seen(spider, r1)
        filter.close_spider(spider)
