import warnings

import pytest
from twisted.trial import unittest

from scrapy import Spider
from scrapy.core.downloader import Slot
from scrapy.exceptions import ScrapyDeprecationWarning
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
