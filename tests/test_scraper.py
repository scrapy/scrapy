import warnings

import pytest
from twisted.trial import unittest

from scrapy import Spider
from scrapy.core.scraper import Slot
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.test import get_crawler


class DummySpider(Spider):
    name = "test"
    start_urls = ["data:,"]

    def parse(self, response):
        pass


class ScraperTest(unittest.TestCase):

    @deferred_f_from_coro_f
    async def test_crawl(self):
        """A crawl should not trigger any deprecation warning."""
        outcome = {}

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]

            def parse(self, response):
                with pytest.warns(ScrapyDeprecationWarning):
                    outcome["active_size"] = (
                        self.crawler.engine.scraper.slot.active_size
                    )

        crawler = get_crawler(TestSpider)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await crawler.crawl()

        with pytest.warns(ScrapyDeprecationWarning):
            expected = crawler.engine.scraper.slot.MIN_RESPONSE_SIZE
        self.assertEqual(outcome["active_size"], expected)

    def test_min_response_time_read(self):
        slot = Slot()
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            actual = slot.MIN_RESPONSE_SIZE
        self.assertEqual(actual, 1024)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            "scrapy.core.scraper.Slot.MIN_RESPONSE_SIZE is deprecated.",
        )

    def test_min_response_time_write(self):
        slot = Slot()
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            slot.MIN_RESPONSE_SIZE = 0
        with pytest.warns(ScrapyDeprecationWarning):
            self.assertEqual(slot.MIN_RESPONSE_SIZE, 0)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            "scrapy.core.scraper.Slot.MIN_RESPONSE_SIZE is deprecated.",
        )

    def test_slot_init_max_active_size_default(self):
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            slot = Slot(max_active_size=5_000_000)
        with pytest.warns(ScrapyDeprecationWarning):
            self.assertEqual(slot.max_active_size, 5_000_000)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            (
                "The max_active_size parameter of scrapy.core.scraper.Slot is "
                "deprecated. Use the RESPONSE_MAX_ACTIVE_SIZE setting instead."
            ),
        )

    def test_slot_init_max_active_size_custom(self):
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            slot = Slot(max_active_size=0)
        with pytest.warns(ScrapyDeprecationWarning):
            self.assertEqual(slot.max_active_size, 0)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            (
                "The max_active_size parameter of scrapy.core.scraper.Slot is "
                "deprecated. Use the RESPONSE_MAX_ACTIVE_SIZE setting instead."
            ),
        )

    def test_max_active_size_read(self):
        slot = Slot()
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            actual = slot.max_active_size
        self.assertEqual(actual, 5_000_000)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            (
                "scrapy.core.scraper.Slot.max_active_size is deprecated. Read "
                "the RESPONSE_MAX_ACTIVE_SIZE setting instead."
            ),
        )

    def test_max_active_size_write(self):
        slot = Slot()
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            slot.max_active_size = 0
        with pytest.warns(ScrapyDeprecationWarning):
            self.assertEqual(slot.max_active_size, 0)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            (
                "scrapy.core.scraper.Slot.max_active_size is deprecated. Set "
                "the RESPONSE_MAX_ACTIVE_SIZE setting instead."
            ),
        )

    def test_active_size_read(self):
        slot = Slot()
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            actual = slot.active_size
        self.assertEqual(actual, 0)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            (
                "scrapy.core.scraper.Slot.active_size is deprecated. Read "
                "scrapy.core.downloader.DownloaderMiddlewareManager.response_active_size "
                "instead."
            ),
        )

    def test_active_size_write(self):
        slot = Slot()
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            slot.active_size = 1
        with pytest.warns(ScrapyDeprecationWarning):
            self.assertEqual(slot.active_size, 1)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            (
                "scrapy.core.scraper.Slot.active_size is deprecated. "
                "scrapy.core.downloader.DownloaderMiddlewareManager.response_active_size "
                "might work as a replacement, but modifying that attribute "
                "might not be a good idea. If you have a use case for it, you "
                "might want to bring it up in a GitHub issue, to discuss with "
                "Scrapy developers if there is a better approach, or some "
                "change we could implement in Scrapy to improve support for "
                "your use case."
            ),
        )

    def test_needs_backout_false(self):
        slot = Slot()
        with pytest.warns(ScrapyDeprecationWarning):
            slot.active_size = 5_000_000
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            actual = slot.needs_backout()
        self.assertEqual(actual, False)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            "scrapy.core.scraper.Slot.needs_backout is deprecated.",
        )

    def test_needs_backout_true(self):
        slot = Slot()
        with pytest.warns(ScrapyDeprecationWarning):
            slot.active_size = 5_000_001
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            actual = slot.needs_backout()
        self.assertEqual(actual, True)
        self.assertEqual(len(warning_messages), 1)
        self.assertEqual(
            str(warning_messages[0].message),
            "scrapy.core.scraper.Slot.needs_backout is deprecated.",
        )
