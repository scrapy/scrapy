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

        await self._test_spider(TestSpider, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_start(self):
        class TestSpider(Spider):
            name = "test"

            async def start(self):
                yield ITEM_A

        await self._test_spider(TestSpider, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_start_subclass(self):
        class BaseSpider(Spider):
            async def start(self):
                yield ITEM_A

        class TestSpider(BaseSpider):
            name = "test"

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

        await self._test_spider(TestSpider, [ITEM_A])

    async def _test_start(self, start_, expected_items=None):
        class TestSpider(Spider):
            name = "test"
            start = start_

        await self._test_spider(TestSpider, expected_items)

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_asyncio_delayed(self):
        async def start(spider):
            await sleep(ASYNC_GEN_ERROR_MINIMUM_SECONDS)
            yield ITEM_A

        await self._test_start(start, [ITEM_A])

    @deferred_f_from_coro_f
    async def test_twisted_delayed(self):
        async def start(spider):
            await maybe_deferred_to_future(
                twisted_sleep(ASYNC_GEN_ERROR_MINIMUM_SECONDS)
            )
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
