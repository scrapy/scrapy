import unittest

from scrapy.http import Request
from scrapy.core.filters import SimplePerDomainFilter, NullFilter


class SimplePerDomainFilterTest(unittest.TestCase):

    def test_filter(self):
        domain = 'scrapytest.org'
        filter = SimplePerDomainFilter()
        filter.open(domain)
        assert domain in filter

        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')

        assert not filter.has(domain, r1)
        assert filter.add(domain, r1)
        assert filter.has(domain, r1)

        assert filter.add(domain, r2)
        assert not filter.add(domain, r3)

        filter.close(domain)
        assert domain not in filter


class NullFilterTest(unittest.TestCase):

    def test_filter(self):
        domain = 'scrapytest.org'
        filter = NullFilter()
        filter.open(domain)

        r1 = Request('http://scrapytest.org/1')
        assert not filter.has(domain, r1)
        assert filter.add(domain, r1)
        assert not filter.has(domain, r1)
        filter.close(domain)
