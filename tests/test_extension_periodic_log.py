import datetime
import unittest

from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.extensions.periodic_log import PeriodicLog

from .spiders import MetaSpider

stats_dump_1 = {
    "log_count/INFO": 10,
    "log_count/WARNING": 1,
    "start_time": datetime.datetime(2023, 6, 16, 8, 59, 18, 993170),
    "scheduler/enqueued/memory": 190,
    "scheduler/enqueued": 190,
    "scheduler/dequeued/memory": 166,
    "scheduler/dequeued": 166,
    "downloader/request_count": 166,
    "downloader/request_method_count/GET": 166,
    "downloader/request_bytes": 56803,
    "downloader/response_count": 150,
    "downloader/response_status_count/200": 150,
    "downloader/response_bytes": 595698,
    "httpcompression/response_bytes": 3186068,
    "httpcompression/response_count": 150,
    "response_received_count": 150,
    "request_depth_max": 9,
    "dupefilter/filtered": 180,
    "item_scraped_count": 140,
}
stats_dump_2 = {
    "log_count/INFO": 12,
    "log_count/WARNING": 1,
    "start_time": datetime.datetime(2023, 6, 16, 8, 59, 18, 993170),
    "scheduler/enqueued/memory": 337,
    "scheduler/enqueued": 337,
    "scheduler/dequeued/memory": 280,
    "scheduler/dequeued": 280,
    "downloader/request_count": 280,
    "downloader/request_method_count/GET": 280,
    "downloader/request_bytes": 95754,
    "downloader/response_count": 264,
    "downloader/response_status_count/200": 264,
    "downloader/response_bytes": 1046274,
    "httpcompression/response_bytes": 5614484,
    "httpcompression/response_count": 264,
    "response_received_count": 264,
    "request_depth_max": 16,
    "dupefilter/filtered": 320,
    "item_scraped_count": 248,
}


class TestPeriodicLog(unittest.TestCase):
    def test_extension_enabled(self):
        extension = PeriodicLog.from_crawler(
            Crawler(
                MetaSpider,
                settings={"PERIODIC_LOG_STATS": True, "LOGSTATS_INTERVAL": 60},
            )
        )
        # Test enabled
        assert extension

        # Raise not configured if not set by settings
        with self.assertRaises(NotConfigured):
            PeriodicLog.from_crawler(Crawler(MetaSpider))

    def test_periodic_log_stats(self):
        pass

    def test_log_delta(self):
        pass

    def test_settings_include(self):
        pass

    def test_settings_exclude(self):
        pass
