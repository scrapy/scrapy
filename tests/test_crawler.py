import warnings
import unittest

from scrapy.crawler import Crawler
from scrapy.settings import Settings
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.misc import load_object


class CrawlerTestCase(unittest.TestCase):

    def setUp(self):
        self.crawler = Crawler(DefaultSpider, Settings())

    def test_deprecated_attribute_spiders(self):
        with warnings.catch_warnings(record=True) as w:
            spiders = self.crawler.spiders
            self.assertEqual(len(w), 1)
            self.assertIn("Crawler.spiders", str(w[0].message))
            sm_cls = load_object(self.crawler.settings['SPIDER_MANAGER_CLASS'])
            self.assertIsInstance(spiders, sm_cls)

            self.crawler.spiders
            self.assertEqual(len(w), 1, "Warn deprecated access only once")
