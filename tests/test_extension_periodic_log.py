import datetime
import typing
import unittest

from scrapy.crawler import Crawler
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


class TestExtPeriodicLog(PeriodicLog):
    def set_a(self):
        self.stats._stats = stats_dump_1

    def set_b(self):
        self.stats._stats = stats_dump_2


def extension(settings=None):
    crawler = Crawler(MetaSpider, settings=settings)
    crawler._apply_settings()
    return TestExtPeriodicLog.from_crawler(crawler)


class TestPeriodicLog(unittest.TestCase):
    def test_extension_enabled(self):
        # Expected that settings for this extension loaded successfully
        # And on certain conditions - extension raising NotConfigured

        # "PERIODIC_LOG_STATS": True -> set to {"enabled": True}
        # due to TypeError exception from settings.getdict
        assert extension({"PERIODIC_LOG_STATS": True, "LOGSTATS_INTERVAL": 60})

        # "PERIODIC_LOG_STATS": "True" -> set to {"enabled": True}
        # due to JSONDecodeError(ValueError) exception from settings.getdict
        assert extension({"PERIODIC_LOG_STATS": "True", "LOGSTATS_INTERVAL": 60})

        # The ame for PERIODIC_LOG_DELTA:
        assert extension({"PERIODIC_LOG_DELTA": True, "LOGSTATS_INTERVAL": 60})
        assert extension({"PERIODIC_LOG_DELTA": "True", "LOGSTATS_INTERVAL": 60})

    def test_log_delta(self):
        def emulate(settings=None):
            spider = MetaSpider()
            ext = extension(settings)
            ext.spider_opened(spider)
            ext.set_a()
            a = ext.log_delta()
            ext.set_a()
            b = ext.log_delta()
            ext.spider_closed(spider, reason="finished")
            return ext, a, b

        def check(settings: dict, condition: typing.Callable):
            ext, a, b = emulate(settings)
            assert list(a["delta"].keys()) == [
                k for k, v in ext.stats._stats.items() if condition(k, v)
            ]
            assert list(b["delta"].keys()) == [
                k for k, v in ext.stats._stats.items() if condition(k, v)
            ]

        # Including all
        check({"PERIODIC_LOG_DELTA": True}, lambda k, v: isinstance(v, (int, float)))

        # include:
        check(
            {"PERIODIC_LOG_DELTA": {"include": ["downloader/"]}},
            lambda k, v: isinstance(v, (int, float)) and "downloader/" in k,
        )

        # include multiple
        check(
            {"PERIODIC_LOG_DELTA": {"include": ["downloader/", "scheduler/"]}},
            lambda k, v: isinstance(v, (int, float))
            and ("downloader/" in k or "scheduler/" in k),
        )

        # exclude
        check(
            {"PERIODIC_LOG_DELTA": {"exclude": ["downloader/"]}},
            lambda k, v: isinstance(v, (int, float)) and "downloader/" not in k,
        )

        # exclude multiple
        check(
            {"PERIODIC_LOG_DELTA": {"exclude": ["downloader/", "scheduler/"]}},
            lambda k, v: isinstance(v, (int, float))
            and ("downloader/" not in k and "scheduler/" not in k),
        )

        # include exclude combined
        check(
            {"PERIODIC_LOG_DELTA": {"include": ["downloader/"], "exclude": ["bytes"]}},
            lambda k, v: isinstance(v, (int, float))
            and ("downloader/" in k and "bytes" not in k),
        )

    def test_log_stats(self):
        def emulate(settings=None):
            spider = MetaSpider()
            ext = extension(settings)
            ext.spider_opened(spider)
            ext.set_a()
            a = ext.log_crawler_stats()
            ext.set_a()
            b = ext.log_crawler_stats()
            ext.spider_closed(spider, reason="finished")
            return ext, a, b

        def check(settings: dict, condition: typing.Callable):
            ext, a, b = emulate(settings)
            assert list(a["stats"].keys()) == [
                k for k, v in ext.stats._stats.items() if condition(k, v)
            ]
            assert list(b["stats"].keys()) == [
                k for k, v in ext.stats._stats.items() if condition(k, v)
            ]

        # Including all
        check({"PERIODIC_LOG_STATS": True}, lambda k, v: True)

        # include:
        check(
            {"PERIODIC_LOG_STATS": {"include": ["downloader/"]}},
            lambda k, v: "downloader/" in k,
        )

        # include multiple
        check(
            {"PERIODIC_LOG_STATS": {"include": ["downloader/", "scheduler/"]}},
            lambda k, v: "downloader/" in k or "scheduler/" in k,
        )

        # exclude
        check(
            {"PERIODIC_LOG_STATS": {"exclude": ["downloader/"]}},
            lambda k, v: "downloader/" not in k,
        )

        # exclude multiple
        check(
            {"PERIODIC_LOG_STATS": {"exclude": ["downloader/", "scheduler/"]}},
            lambda k, v: "downloader/" not in k and "scheduler/" not in k,
        )

        # include exclude combined
        check(
            {"PERIODIC_LOG_STATS": {"include": ["downloader/"], "exclude": ["bytes"]}},
            lambda k, v: "downloader/" in k and "bytes" not in k,
        )
        #
