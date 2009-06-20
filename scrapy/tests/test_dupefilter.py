import unittest

from scrapy.http import Request
from scrapy.contrib.dupefilter import RequestFingerprintDupeFilter, NullDupeFilter


class RequestFingerprintDupeFilterTest(unittest.TestCase):

    def test_filter(self):
        domain = 'scrapytest.org'
        filter = RequestFingerprintDupeFilter()
        filter.open_domain(domain)

        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')

        assert not filter.request_seen(domain, r1)
        assert filter.request_seen(domain, r1)

        assert not filter.request_seen(domain, r2)
        assert filter.request_seen(domain, r3)

        filter.close_domain(domain)


class NullDupeFilterTest(unittest.TestCase):

    def test_filter(self):
        domain = 'scrapytest.org'
        filter = NullDupeFilter()
        filter.open_domain(domain)

        r1 = Request('http://scrapytest.org/1')
        assert not filter.request_seen(domain, r1)
        filter.close_domain(domain)
