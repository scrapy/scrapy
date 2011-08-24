import unittest

from scrapy.http import Request
from scrapy.dupefilter import RFPDupeFilter


class RFPDupeFilterTest(unittest.TestCase):

    def test_filter(self):
        filter = RFPDupeFilter()
        filter.open()

        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')

        assert not filter.request_seen(r1)
        assert filter.request_seen(r1)

        assert not filter.request_seen(r2)
        assert filter.request_seen(r3)

        filter.close('finished')
