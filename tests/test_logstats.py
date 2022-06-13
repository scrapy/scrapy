import unittest

from scrapy.extensions.logstats import LogStats
from scrapy.utils.test import get_crawler

from tests.spiders import SimpleSpider


class TestLogStats(unittest.TestCase):
    def setUp(self):
        self.crawler = get_crawler(SimpleSpider)
        self.spider = self.crawler._create_spider('spidey')
        self.stats = self.crawler.stats

        self.stats.set_value("response_received_count", 4802)
        self.stats.set_value("item_scraped_count", 3201)

    def test_stats_calculations(self):
        logstats = LogStats.from_crawler(self.crawler)

        with self.assertRaises(AttributeError):
            logstats.pagesprev
            logstats.itemsprev

        logstats.spider_opened(self.spider)
        self.assertEqual(logstats.pagesprev, 4802)
        self.assertEqual(logstats.itemsprev, 3201)

        logstats.calculate_stats()
        self.assertEqual(logstats.items, 3201)
        self.assertEqual(logstats.pages, 4802)
        self.assertEqual(logstats.irate, 0.0)
        self.assertEqual(logstats.prate, 0.0)
        self.assertEqual(logstats.pagesprev, 4802)
        self.assertEqual(logstats.itemsprev, 3201)

        # Simulate what happens after a minute
        self.stats.set_value("response_received_count", 5187)
        self.stats.set_value("item_scraped_count", 3492)
        logstats.calculate_stats()
        self.assertEqual(logstats.items, 3492)
        self.assertEqual(logstats.pages, 5187)
        self.assertEqual(logstats.irate, 291.0)
        self.assertEqual(logstats.prate, 385.0)
        self.assertEqual(logstats.pagesprev, 5187)
        self.assertEqual(logstats.itemsprev, 3492)

        # Simulate when spider closes
        self.stats.set_value("start_time", 1655100172088)
        self.stats.set_value("finished_time", 1655101972088) # 30 mins diff
        logstats.spider_closed(self.spider, "test reason")
        self.assertEqual(self.stats.get_value("responses_per_minute"), 172.9)
        self.assertEqual(self.stats.get_value("items_per_minute"), 116.4)
