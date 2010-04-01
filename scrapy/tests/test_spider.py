from __future__ import with_statement

import sys
import warnings

from twisted.trial import unittest

from scrapy.spider import BaseSpider
from scrapy.contrib.dupefilter import RequestFingerprintDupeFilter, NullDupeFilter

class OldSpider(BaseSpider):

    domain_name = 'example.com'
    extra_domain_names = ('example.org', 'example.net')

class NewSpider(BaseSpider):

    name = 'example.com'
    allowed_domains = ('example.org', 'example.net')


class SpiderTest(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter("always")

    def tearDown(self):
        warnings.resetwarnings()

    def test_sep12_deprecation_warnings(self):
        if sys.version_info[:2] < (2, 6):
            # warnings.catch_warnings() was added in Python 2.6
            raise unittest.SkipTest("This test requires Python 2.6+")
        with warnings.catch_warnings(record=True) as w:
            spider = OldSpider()
            self.assertEqual(len(w), 2) # one for domain_name & one for extra_domain_names
            self.assert_(issubclass(w[-1].category, DeprecationWarning))

    def test_sep12_backwards_compatibility(self):
        spider = OldSpider()
        self.assertEqual(spider.name, 'example.com')
        self.assert_('example.com' in spider.allowed_domains, spider.allowed_domains)
        self.assert_('example.org' in spider.allowed_domains, spider.allowed_domains)
        self.assert_('example.net' in spider.allowed_domains, spider.allowed_domains)

        spider = NewSpider()
        self.assertEqual(spider.domain_name, 'example.com')
        self.assert_('example.org' in spider.extra_domain_names, spider.extra_domain_names)
        self.assert_('example.net' in spider.extra_domain_names, spider.extra_domain_names)

    def test_base_spider(self):
        spider = BaseSpider("example.com")
        self.assertEqual(spider.name, 'example.com')
        self.assertEqual(spider.start_urls, [])
        self.assertEqual(spider.allowed_domains, [])

