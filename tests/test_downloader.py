import warnings

import pytest
from twisted.trial import unittest

from scrapy import Request, Spider
from scrapy.core.downloader import Slot
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Response
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.test import get_crawler


class SlotTest(unittest.TestCase):
    def test_repr(self):
        slot = Slot(concurrency=8, delay=0.1, randomize_delay=True)
        self.assertEqual(
            repr(slot),
            "Slot(concurrency=8, delay=0.10, randomize_delay=True, throttle=None)",
        )


class OfflineSpider(Spider):
    name = "offline"
    start_urls = ["data:,"]

    def parse(self, response):
        pass


class gt:

    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return other > self.value

    def __repr__(self):
        return f">{self.value}"


class ResponseMaxActiveSizeTest(unittest.TestCase):

    @deferred_f_from_coro_f
    async def test_default(self):
        """A crawl without custom settings has its effective response max
        active size set to 5 000 000, and triggers no deprecation warning."""
        crawler = get_crawler(OfflineSpider)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await crawler.crawl()
        self.assertEqual(crawler.engine.downloader._response_max_active_size, 5_000_000)

    @deferred_f_from_coro_f
    async def test_custom(self):
        """Setting RESPONSE_MAX_ACTIVE_SIZE to a custom value changes the
        effective response max active size."""
        crawler = get_crawler(
            OfflineSpider, settings_dict={"RESPONSE_MAX_ACTIVE_SIZE": 0}
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await crawler.crawl()
        self.assertEqual(crawler.engine.downloader._response_max_active_size, 0)

    @deferred_f_from_coro_f
    async def test_deprecated_default(self):
        """Setting SCRAPER_SLOT_MAX_ACTIVE_SIZE triggers a deprecation warning,
        even if it is the default value."""
        crawler = get_crawler(
            OfflineSpider, settings_dict={"SCRAPER_SLOT_MAX_ACTIVE_SIZE": 5_000_000}
        )
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            await crawler.crawl()
        self.assertEqual(crawler.engine.downloader._response_max_active_size, 5_000_000)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            (
                "The SCRAPER_SLOT_MAX_ACTIVE_SIZE setting is deprecated, use "
                "RESPONSE_MAX_ACTIVE_SIZE instead."
            ),
        )

    @deferred_f_from_coro_f
    async def test_deprecated_custom(self):
        """Setting SCRAPER_SLOT_MAX_ACTIVE_SIZE to a custom value triggers a
        deprecation warning, and changes the effective response max active
        size."""
        crawler = get_crawler(
            OfflineSpider, settings_dict={"SCRAPER_SLOT_MAX_ACTIVE_SIZE": 0}
        )
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            await crawler.crawl()
        self.assertEqual(crawler.engine.downloader._response_max_active_size, 0)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            (
                "The SCRAPER_SLOT_MAX_ACTIVE_SIZE setting is deprecated, use "
                "RESPONSE_MAX_ACTIVE_SIZE instead."
            ),
        )

    @deferred_f_from_coro_f
    async def test_both(self):
        """Setting RESPONSE_MAX_ACTIVE_SIZE and SCRAPER_SLOT_MAX_ACTIVE_SIZE to
        different values with the same setting priority triggers a deprecation
        warning about SCRAPER_SLOT_MAX_ACTIVE_SIZE and makes the value of
        RESPONSE_MAX_ACTIVE_SIZE the effective response max active size."""
        crawler = get_crawler(
            OfflineSpider,
            settings_dict={
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
                "SCRAPER_SLOT_MAX_ACTIVE_SIZE": 2,
            },
        )
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            await crawler.crawl()
        self.assertEqual(crawler.engine.downloader._response_max_active_size, 1)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            (
                "The SCRAPER_SLOT_MAX_ACTIVE_SIZE setting is deprecated, use "
                "RESPONSE_MAX_ACTIVE_SIZE instead."
            ),
        )

    @deferred_f_from_coro_f
    async def test_both_deprecated_priority(self):
        """Setting RESPONSE_MAX_ACTIVE_SIZE and SCRAPER_SLOT_MAX_ACTIVE_SIZE to
        different values and SCRAPER_SLOT_MAX_ACTIVE_SIZE with a higher
        priority triggers a deprecation warning about
        SCRAPER_SLOT_MAX_ACTIVE_SIZE but also makes the value of
        SCRAPER_SLOT_MAX_ACTIVE_SIZE the effective response max active size."""

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]

            @classmethod
            def update_settings(cls, settings):
                settings.set("RESPONSE_MAX_ACTIVE_SIZE", 1, priority=100)
                settings.set("SCRAPER_SLOT_MAX_ACTIVE_SIZE", 2, priority=101)

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            await crawler.crawl()
        self.assertEqual(crawler.engine.downloader._response_max_active_size, 2)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            (
                "The SCRAPER_SLOT_MAX_ACTIVE_SIZE setting is deprecated, use "
                "RESPONSE_MAX_ACTIVE_SIZE instead."
            ),
        )


class RequestBackoutTest(unittest.TestCase):

    @pytest.fixture(autouse=True)
    def use_caplog(self, caplog):
        self.caplog = caplog

    @deferred_f_from_coro_f
    async def test_none(self):

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await crawler.crawl()

        matching_log_count = 0
        for log_record in self.caplog.records:
            if (
                str(log_record.msg).startswith("The active response size")
                and log_record.levelname == "INFO"
            ):
                matching_log_count += 1
        self.assertEqual(matching_log_count, 0)

        stats = {
            k: v
            for k, v in crawler.stats.get_stats().items()
            if k.startswith("request_backouts/")
        }
        self.assertEqual(stats, {})

    @deferred_f_from_coro_f
    async def test_concurrency(self):

        class SlowDown:
            """Downloader middleware that returns a non-instant deferred from
            process_request, to force need_backout calls to happen at that
            point."""

            def process_request(self, request, spider):
                from twisted.internet import reactor
                from twisted.internet.defer import Deferred

                d = Deferred()
                reactor.callLater(0, d.callback, None)
                return d

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "CONCURRENT_REQUESTS": 1,
                "DOWNLOADER_MIDDLEWARES": {SlowDown: 0},
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await crawler.crawl()

        matching_log_count = 0
        for log_record in self.caplog.records:
            if (
                str(log_record.msg).startswith("The active response size")
                and log_record.levelname == "INFO"
            ):
                matching_log_count += 1
        self.assertEqual(matching_log_count, 0)

        expected_stats = {
            "request_backouts/concurrency": gt(0),
            "request_backouts/total": gt(0),
            "request_backouts/total_per_second": gt(0),
        }
        actual_stats = {
            k: v
            for k, v in crawler.stats.get_stats().items()
            if k.startswith("request_backouts/")
        }
        self.assertEqual(expected_stats, actual_stats)

    @deferred_f_from_coro_f
    async def test_response_size(self):

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,a"]
            custom_settings = {
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await crawler.crawl()

        matching_log_count = 0
        for log_record in self.caplog.records:
            if (
                str(log_record.msg).startswith("The active response size")
                and log_record.levelname == "INFO"
            ):
                matching_log_count += 1
        self.assertEqual(matching_log_count, 1)

        expected_stats = {
            # Test > 1, if 1 then we are not really making sure that the INFO
            # message above is logged only once in a scenario where active size
            # is checked more than once.
            "request_backouts/response_max_active_size": gt(1),
            "request_backouts/total": gt(0),
            "request_backouts/total_per_second": gt(0),
        }
        actual_stats = {
            k: v
            for k, v in crawler.stats.get_stats().items()
            if k.startswith("request_backouts/")
        }
        self.assertEqual(expected_stats, actual_stats)

    @deferred_f_from_coro_f
    async def test_response_size_process_request(self):

        class DownloaderMiddleware:

            def process_request(self, request, spider):
                return Response("https://example.com", body=b"a")

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "DOWNLOADER_MIDDLEWARES": {DownloaderMiddleware: 0},
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await crawler.crawl()

        matching_log_count = 0
        for log_record in self.caplog.records:
            if (
                str(log_record.msg).startswith("The active response size")
                and log_record.levelname == "INFO"
            ):
                matching_log_count += 1
        self.assertEqual(matching_log_count, 1)

        expected_stats = {
            "request_backouts/response_max_active_size": gt(0),
            "request_backouts/total": gt(0),
            "request_backouts/total_per_second": gt(0),
        }
        actual_stats = {
            k: v
            for k, v in crawler.stats.get_stats().items()
            if k.startswith("request_backouts/")
        }
        self.assertEqual(expected_stats, actual_stats)

    @deferred_f_from_coro_f
    async def test_response_size_process_response(self):

        class DownloaderMiddleware:

            def process_response(self, request, response, spider):
                return Response("https://example.com", body=b"a")

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "DOWNLOADER_MIDDLEWARES": {DownloaderMiddleware: 0},
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await crawler.crawl()

        matching_log_count = 0
        for log_record in self.caplog.records:
            if (
                str(log_record.msg).startswith("The active response size")
                and log_record.levelname == "INFO"
            ):
                matching_log_count += 1
        self.assertEqual(matching_log_count, 1)

        expected_stats = {
            "request_backouts/response_max_active_size": gt(0),
            "request_backouts/total": gt(0),
            "request_backouts/total_per_second": gt(0),
        }
        actual_stats = {
            k: v
            for k, v in crawler.stats.get_stats().items()
            if k.startswith("request_backouts/")
        }
        self.assertEqual(expected_stats, actual_stats)

    @deferred_f_from_coro_f
    async def test_response_size_process_exception(self):

        class DownloaderMiddleware1:

            def process_exception(self, request, exception, spider):
                return Response("https://example.com", body=b"a")

        class DownloaderMiddleware2:

            def process_request(self, request, spider):
                raise ValueError

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "DOWNLOADER_MIDDLEWARES": {
                    DownloaderMiddleware1: 0,
                    DownloaderMiddleware2: 1,
                },
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await crawler.crawl()

        matching_log_count = 0
        for log_record in self.caplog.records:
            if (
                str(log_record.msg).startswith("The active response size")
                and log_record.levelname == "INFO"
            ):
                matching_log_count += 1
        self.assertEqual(matching_log_count, 1)

        expected_stats = {
            "request_backouts/response_max_active_size": gt(0),
            "request_backouts/total": gt(0),
            "request_backouts/total_per_second": gt(0),
        }
        actual_stats = {
            k: v
            for k, v in crawler.stats.get_stats().items()
            if k.startswith("request_backouts/")
        }
        self.assertEqual(expected_stats, actual_stats)

    @deferred_f_from_coro_f
    async def test_response_size_download(self):
        """Ensure that responses from engine.download calls are also taken into
        account for the RESPONSE_MAX_ACTIVE_SIZE setting."""

        class SlowDown:
            """Item pipeline that returns a non-instant deferred, to force
            need_backout calls to happen at that point."""

            def process_item(self, item, spider):
                from twisted.internet import reactor
                from twisted.internet.defer import Deferred

                d = Deferred()
                reactor.callLater(0, d.callback, {})
                return d

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "ITEM_PIPELINES": {SlowDown: 0},
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            async def parse(self, response):
                response = await self.crawler.engine.download(Request("data:,a"))
                yield {"response": response}

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await crawler.crawl()

        matching_log_count = 0
        for log_record in self.caplog.records:
            if (
                str(log_record.msg).startswith("The active response size")
                and log_record.levelname == "INFO"
            ):
                matching_log_count += 1
        self.assertEqual(matching_log_count, 1)

        expected_stats = {
            "request_backouts/response_max_active_size": gt(0),
            "request_backouts/total": gt(0),
            "request_backouts/total_per_second": gt(0),
        }
        actual_stats = {
            k: v
            for k, v in crawler.stats.get_stats().items()
            if k.startswith("request_backouts/")
        }
        self.assertEqual(expected_stats, actual_stats)
