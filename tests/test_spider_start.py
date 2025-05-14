import warnings
from asyncio import sleep

import pytest
from testfixtures import LogCapture
from twisted.trial.unittest import TestCase

from scrapy import Spider, signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from .utils import twisted_sleep

SLEEP_SECONDS = 0.1

ITEM_A = {"id": "a"}
ITEM_B = {"id": "b"}


class MainTestCase(TestCase):
    async def _test_spider(self, spider, expected_items=None):
        actual_items = []
        expected_items = [] if expected_items is None else expected_items

        def track_item(item, response, spider):
            actual_items.append(item)

        crawler = get_crawler(spider)
        crawler.signals.connect(track_item, signals.item_scraped)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        assert actual_items == expected_items

    @deferred_f_from_coro_f
    async def test_start_urls(self):
        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]

            async def parse(self, response):
                yield ITEM_A

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_spider(TestSpider, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_start(self):
        class TestSpider(Spider):
            name = "test"

            async def start(self):
                yield ITEM_A

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_spider(TestSpider, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_start_subclass(self):
        class BaseSpider(Spider):
            async def start(self):
                yield ITEM_A

        class TestSpider(BaseSpider):
            name = "test"

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_spider(TestSpider, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_deprecated(self):
        class TestSpider(Spider):
            name = "test"

            def start_requests(self):
                yield ITEM_A

        with pytest.warns(ScrapyDeprecationWarning):
            await self._test_spider(TestSpider, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_deprecated_subclass(self):
        class BaseSpider(Spider):
            def start_requests(self):
                yield ITEM_A

        class TestSpider(BaseSpider):
            name = "test"

        # The warning must be about the base class and not the subclass.
        with pytest.warns(ScrapyDeprecationWarning, match="BaseSpider"):
            await self._test_spider(TestSpider, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_universal(self):
        class TestSpider(Spider):
            name = "test"

            async def start(self):
                yield ITEM_A

            def start_requests(self):
                yield ITEM_B

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_spider(TestSpider, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_universal_subclass(self):
        class BaseSpider(Spider):
            async def start(self):
                yield ITEM_A

            def start_requests(self):
                yield ITEM_B

        class TestSpider(BaseSpider):
            name = "test"

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_spider(TestSpider, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_start_deprecated_super(self):
        class TestSpider(Spider):
            name = "test"

            async def start(self):
                for item_or_request in super().start_requests():
                    yield item_or_request

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"use Spider\.start\(\) instead"
        ) as messages:
            await self._test_spider(TestSpider, [])
        assert messages[0].filename.endswith("test_spider_start.py")

    async def _test_start(self, start_, expected_items=None):
        class TestSpider(Spider):
            name = "test"
            start = start_

        await self._test_spider(TestSpider, expected_items)

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_asyncio_delayed(self):
        async def start(spider):
            await sleep(SLEEP_SECONDS)
            yield ITEM_A

        await self._test_start(start, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_twisted_delayed(self):
        async def start(spider):
            await maybe_deferred_to_future(twisted_sleep(SLEEP_SECONDS))
            yield ITEM_A

        await self._test_start(start, [ITEM_A])

    # Exceptions

    @deferred_f_from_coro_f
    async def test_deprecated_non_generator_exception(self):
        class TestSpider(Spider):
            name = "test"

            def start_requests(self):
                raise RuntimeError

        with (
            LogCapture() as log,
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"defines the deprecated start_requests\(\) method",
            ),
        ):
            await self._test_spider(TestSpider, [])

        assert "in start_requests\n    raise RuntimeError" in str(log)
