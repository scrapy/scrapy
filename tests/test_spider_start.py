import warnings
from asyncio import sleep

import pytest
from testfixtures import LogCapture
from twisted.internet.defer import Deferred
from twisted.trial.unittest import TestCase

from scrapy import Spider, signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from . import TWISTED_KEEPS_TRACEBACKS
from .test_scheduler import MemoryScheduler

SLEEP_SECONDS = 0.1
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

    async def _test_start(self, start_fn, expected_items=None):
        class TestSpider(Spider):
            name = "test"
            start = start_fn

        await self._test_spider(TestSpider, expected_items)

    # Basic usage

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

    # Bad definitions.

    @deferred_f_from_coro_f
    async def test_start_non_gen(self):
        async def start(spider):
            return

        with LogCapture() as log, warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_start(start, [])

        assert ".start must be an asynchronous generator" in str(log)

    @deferred_f_from_coro_f
    async def test_start_sync(self):
        def start(spider):
            return
            yield

        with LogCapture() as log, warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_start(start, [])

        assert ".start must be an asynchronous generator" in str(log)

    @deferred_f_from_coro_f
    async def test_start_sync_non_gen(self):
        def start(spider):
            return []

        with LogCapture() as log, warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_start(start, [])

        assert ".start must be an asynchronous generator" in str(log)

    @deferred_f_from_coro_f
    async def test_start_requests_non_gen_exception(self):
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

    @deferred_f_from_coro_f
    async def test_start_url(self):
        class TestSpider(Spider):
            name = "test"
            start_url = "https://toscrape.com"

        with LogCapture() as log:
            await self._test_spider(TestSpider, [])

        assert "Error while reading start items and requests" in str(log), log
        assert "found 'start_url' attribute instead, did you miss an 's'?" in str(
            log
        ), log

    @deferred_f_from_coro_f
    async def test_exception_before_yield(self):
        async def start(spider):
            raise RuntimeError
            yield  # pylint: disable=unreachable

        with LogCapture() as log:
            await self._test_start(start, [])

        if TWISTED_KEEPS_TRACEBACKS:
            assert "in start\n    raise RuntimeError" in str(log), log
        else:
            assert "in _process_next_seed\n    seed =" in str(log), log

    @deferred_f_from_coro_f
    async def test_exception_after_yield(self):
        async def start(spider):
            yield ITEM_A
            raise RuntimeError

        with LogCapture() as log:
            await self._test_start(start, [ITEM_A])

        if TWISTED_KEEPS_TRACEBACKS:
            assert "in start\n    raise RuntimeError" in str(log), log
        else:
            assert "in _process_next_seed\n    seed =" in str(log), log

    @deferred_f_from_coro_f
    async def test_bad_definition_continuance(self):
        """Even if start (or process_start) are not correctly defined, blocking
        the iteration of start items and requests, requests from the scheduler
        are still consumed."""

        class TestScheduler(MemoryScheduler):
            queue = ["data:,"]

        class TestSpider(Spider):
            name = "test"

            async def start(self):
                return

            async def parse(self, response):
                yield ITEM_A

        settings = {"SCHEDULER": TestScheduler}

        with LogCapture() as log, warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_spider(TestSpider, [ITEM_A], settings=settings)

        assert ".start must be an asynchronous generator" in str(log), log
