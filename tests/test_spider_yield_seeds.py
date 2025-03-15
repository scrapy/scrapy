from asyncio import sleep

import pytest
from testfixtures import LogCapture
from twisted.internet.defer import Deferred
from twisted.trial.unittest import TestCase

from scrapy import Spider, signals
from scrapy.core.engine import ExecutionEngine
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from .test_scheduler import MemoryScheduler

# These are the minimum seconds necessary to wait to reproduce the issue that
# has been solved by catching the RuntimeError exception in the
# ExecutionEngine._next_request() method. A lower value makes these tests pass
# even if we remove that exception handling, but they start failing with this
# much delay.
ASYNC_GEN_ERROR_MINIMUM_SECONDS = ExecutionEngine._SLOT_HEARTBEAT_INTERVAL + 0.01

ITEM_A = {"id": "a"}
ITEM_B = {"id": "b"}


def twisted_sleep(seconds):
    from twisted.internet import reactor

    d = Deferred()
    reactor.callLater(seconds, d.callback, None)
    return d


class MainTestCase(TestCase):
    # Utility methods

    async def _test_spider(self, spider, expected_items=None, settings=None):
        actual_items = []
        expected_items = [] if expected_items is None else expected_items
        settings = settings or {}

        def track_item(item, response, spider):
            actual_items.append(item)

        crawler = get_crawler(spider, settings_dict=settings)
        crawler.signals.connect(track_item, signals.item_scraped)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        assert actual_items == expected_items, f"{actual_items=} != {expected_items=}"

    async def _test_yield_seeds(self, yield_seeds_, expected_items=None):
        class TestSpider(Spider):
            name = "test"
            yield_seeds = yield_seeds_

        await self._test_spider(TestSpider, expected_items)

    # Basic usage

    @deferred_f_from_coro_f
    async def test_start_urls(self):
        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]

            async def parse(self, response):
                yield ITEM_A

        await self._test_spider(TestSpider, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_main(self):
        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                yield ITEM_A

        await self._test_spider(TestSpider, [ITEM_A])

    # Deprecation of start_requests and universal implementation support.

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

            async def yield_seeds(self):
                yield ITEM_A

            def start_requests(self):
                yield ITEM_B

        await self._test_spider(TestSpider, [ITEM_A])

    # Delays.

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_asyncio_delayed(self):
        async def yield_seeds(spider):
            await sleep(ASYNC_GEN_ERROR_MINIMUM_SECONDS)
            yield ITEM_A

        await self._test_yield_seeds(yield_seeds, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_twisted_delayed(self):
        async def yield_seeds(spider):
            await maybe_deferred_to_future(
                twisted_sleep(ASYNC_GEN_ERROR_MINIMUM_SECONDS)
            )
            yield ITEM_A

        await self._test_yield_seeds(yield_seeds, [ITEM_A])

    # Bad definitions.

    @deferred_f_from_coro_f
    async def test_async_function(self):
        async def yield_seeds(spider):
            return

        with LogCapture() as log:
            await self._test_yield_seeds(yield_seeds, [])

        assert ".yield_seeds must be an async generator function" in str(log)

    @deferred_f_from_coro_f
    async def test_sync_function(self):
        def yield_seeds(spider):
            return []

        with LogCapture() as log:
            await self._test_yield_seeds(yield_seeds, [])

        assert ".yield_seeds must be an async generator function" in str(log)

    @deferred_f_from_coro_f
    async def test_sync_generator(self):
        def yield_seeds(spider):
            return
            yield

        with LogCapture() as log:
            await self._test_yield_seeds(yield_seeds, [])

        assert ".yield_seeds must be an async generator function" in str(log)

    @deferred_f_from_coro_f
    async def test_bad_definition_continuance(self):
        """Even if yield_seeds (or process_seeds) are not correctly defined,
        blocking the iteration of seeds, requests from the scheduler are still
        consumed."""

        class TestScheduler(MemoryScheduler):
            queue = ["data:,"]

        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                return

            async def parse(self, response):
                yield ITEM_A

        settings = {"SCHEDULER": TestScheduler}

        with LogCapture() as log:
            await self._test_spider(TestSpider, [ITEM_A], settings=settings)

        assert ".yield_seeds must be an async generator function" in str(log), log

    # Exceptions during iteration.

    @deferred_f_from_coro_f
    async def test_exception_before_yield(self):
        async def yield_seeds(spider):
            raise RuntimeError
            yield  # pylint: disable=unreachable

        with LogCapture() as log:
            await self._test_yield_seeds(yield_seeds, [])

        assert "in yield_seeds\n    raise RuntimeError" in str(log), log

    @deferred_f_from_coro_f
    async def test_exception_after_yield(self):
        async def yield_seeds(spider):
            yield ITEM_A
            raise RuntimeError

        with LogCapture() as log:
            await self._test_yield_seeds(yield_seeds, [ITEM_A])

        assert "in yield_seeds\n    raise RuntimeError" in str(log), log

    @deferred_f_from_coro_f
    async def test_start_url(self):
        class TestSpider(Spider):
            name = "test"
            start_url = "https://toscrape.com"

        with LogCapture() as log:
            await self._test_spider(TestSpider, [])

        assert "Error while reading seeds" in str(log), log
        assert "found 'start_url' attribute instead, did you miss an 's'?" in str(
            log
        ), log
