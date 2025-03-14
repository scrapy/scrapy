from asyncio import sleep

import pytest
from testfixtures import LogCapture
from twisted.trial.unittest import TestCase

from scrapy import Spider, signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from .test_spider_yield_seeds import ASYNC_GEN_ERROR_MINIMUM_SECONDS, twisted_sleep

ITEM_A = {"id": "a"}
ITEM_B = {"id": "b"}
ITEM_C = {"id": "c"}
ITEM_D = {"id": "d"}


class AsyncioSleepSpiderMiddleware:
    async def process_seeds(self, seeds):
        await sleep(ASYNC_GEN_ERROR_MINIMUM_SECONDS)
        async for seed in seeds:
            yield seed


class NoOpSpiderMiddleware:
    async def process_seeds(self, seeds):
        async for seed in seeds:
            yield seed


class TwistedSleepSpiderMiddleware:
    async def process_seeds(self, seeds):
        await maybe_deferred_to_future(twisted_sleep(ASYNC_GEN_ERROR_MINIMUM_SECONDS))
        async for seed in seeds:
            yield seed


class UniversalSpiderMiddleware:
    async def process_seeds(self, seeds):
        async for seed in seeds:
            yield seed

    def process_start_requests(self, start_requests, spider):
        raise NotImplementedError


# Spiders and spider middlewares for MainTestCase._test_wrap


class ModernWrapSpider(Spider):
    name = "test"

    async def yield_seeds(self):
        yield ITEM_B


class UniversalWrapSpider(Spider):
    name = "test"

    async def yield_seeds(self):
        yield ITEM_B

    def start_requests(self):
        yield ITEM_D


class DeprecatedWrapSpider(Spider):
    name = "test"

    def start_requests(self):
        yield ITEM_B


class ModernWrapSpiderMiddleware:
    async def process_seeds(self, seeds):
        yield ITEM_A
        async for seed in seeds:
            yield seed
        yield ITEM_C


class UniversalWrapSpiderMiddleware:
    async def process_seeds(self, seeds):
        yield ITEM_A
        async for seed in seeds:
            yield seed
        yield ITEM_C

    def process_start_requests(self, seeds, spider):
        yield ITEM_A
        yield from seeds
        yield ITEM_C


class DeprecatedWrapSpiderMiddleware:
    def process_start_requests(self, seeds, spider):
        yield ITEM_A
        yield from seeds
        yield ITEM_C


class MainTestCase(TestCase):
    # Helper methods

    async def _test(self, spider_middlewares, spider_cls, expected_items):
        actual_items = []

        def track_item(item, response, spider):
            actual_items.append(item)

        settings = {
            "SPIDER_MIDDLEWARES": {cls: n for n, cls in enumerate(spider_middlewares)},
        }
        crawler = get_crawler(spider_cls, settings_dict=settings)
        crawler.signals.connect(track_item, signals.item_scraped)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        assert actual_items == expected_items, f"{actual_items=} != {expected_items=}"

    async def _test_process_seeds(self, _process_seeds, expected_items=None):
        class TestSpiderMiddleware:
            process_seeds = _process_seeds

        class TestSpider(Spider):
            name = "test"

        await self._test([TestSpiderMiddleware], TestSpider, expected_items)

    # Deprecation and universal

    async def _test_wrap(self, spider_middleware, spider_cls, expected_items=None):
        expected_items = (
            [ITEM_A, ITEM_B, ITEM_C] if expected_items is None else expected_items
        )
        await self._test([spider_middleware], spider_cls, expected_items)

    @deferred_f_from_coro_f
    async def test_modern_mw_modern_spider(self):
        await self._test_wrap(ModernWrapSpiderMiddleware, ModernWrapSpider)

    @deferred_f_from_coro_f
    async def test_modern_mw_universal_spider(self):
        await self._test_wrap(ModernWrapSpiderMiddleware, UniversalWrapSpider)

    @deferred_f_from_coro_f
    async def test_modern_mw_deprecated_spider(self):
        with pytest.warns(
            ScrapyDeprecationWarning, match=r"deprecated start_requests\(\)"
        ):
            await self._test_wrap(ModernWrapSpiderMiddleware, DeprecatedWrapSpider)

    @deferred_f_from_coro_f
    async def test_universal_mw_modern_spider(self):
        await self._test_wrap(UniversalWrapSpiderMiddleware, ModernWrapSpider)

    @deferred_f_from_coro_f
    async def test_universal_mw_universal_spider(self):
        await self._test_wrap(UniversalWrapSpiderMiddleware, UniversalWrapSpider)

    @deferred_f_from_coro_f
    async def test_universal_mw_deprecated_spider(self):
        with pytest.warns(
            ScrapyDeprecationWarning, match=r"deprecated start_requests\(\)"
        ):
            await self._test_wrap(UniversalWrapSpiderMiddleware, DeprecatedWrapSpider)

    @deferred_f_from_coro_f
    async def test_deprecated_mw_modern_spider(self):
        with (
            LogCapture() as log,
            pytest.warns(
                ScrapyDeprecationWarning, match=r"deprecated process_start_requests\(\)"
            ),
        ):
            await self._test_wrap(
                DeprecatedWrapSpiderMiddleware, ModernWrapSpider, expected_items=[]
            )

        assert "only compatible with (deprecated) spiders" in str(log)

    @deferred_f_from_coro_f
    async def test_deprecated_mw_universal_spider(self):
        with pytest.warns(
            ScrapyDeprecationWarning, match=r"deprecated process_start_requests\(\)"
        ):
            await self._test_wrap(
                DeprecatedWrapSpiderMiddleware,
                UniversalWrapSpider,
                [ITEM_A, ITEM_D, ITEM_C],
            )

    @deferred_f_from_coro_f
    async def test_deprecated_mw_deprecated_spider(self):
        with (
            pytest.warns(
                ScrapyDeprecationWarning, match=r"deprecated process_start_requests\(\)"
            ),
            pytest.warns(
                ScrapyDeprecationWarning, match=r"deprecated start_requests\(\)"
            ),
        ):
            await self._test_wrap(DeprecatedWrapSpiderMiddleware, DeprecatedWrapSpider)

    # Sleep tests

    async def _test_sleep(self, spider_middlewares):
        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                yield ITEM_A

        await self._test(spider_middlewares, TestSpider, [ITEM_A])

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_asyncio_sleep_single(self):
        await self._test_sleep([AsyncioSleepSpiderMiddleware])

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_asyncio_sleep_multiple(self):
        await self._test_sleep(
            [NoOpSpiderMiddleware, AsyncioSleepSpiderMiddleware, NoOpSpiderMiddleware]
        )

    @deferred_f_from_coro_f
    async def test_twisted_sleep_single(self):
        await self._test_sleep([TwistedSleepSpiderMiddleware])

    @deferred_f_from_coro_f
    async def test_twisted_sleep_multiple(self):
        await self._test_sleep(
            [NoOpSpiderMiddleware, TwistedSleepSpiderMiddleware, NoOpSpiderMiddleware]
        )

    # Bad definitions.

    @deferred_f_from_coro_f
    async def test_async_function(self):
        async def process_seeds(mw, seeds):
            return

        with LogCapture() as log:
            await self._test_process_seeds(process_seeds, [])

        assert ".process_seeds must be an async generator function" in str(log), log

    @deferred_f_from_coro_f
    async def test_sync_function(self):
        def process_seeds(mw, spider):
            return []

        with LogCapture() as log:
            await self._test_process_seeds(process_seeds, [])

        assert ".process_seeds must be an async generator function" in str(log)

    @deferred_f_from_coro_f
    async def test_sync_generator(self):
        def process_seeds(mw, spider):
            return
            yield

        with LogCapture() as log:
            await self._test_process_seeds(process_seeds, [])

        assert ".process_seeds must be an async generator function" in str(log)

    # Exceptions during iteration.

    @deferred_f_from_coro_f
    async def test_exception_before_yield(self):
        async def process_seeds(mw, seeds):
            raise RuntimeError
            yield

        with LogCapture() as log:
            await self._test_process_seeds(process_seeds, [])

        assert "in process_seeds\n    raise RuntimeError" in str(log), log

    @deferred_f_from_coro_f
    async def test_exception_after_yield(self):
        async def process_seeds(mw, spider):
            yield ITEM_A
            raise RuntimeError

        with LogCapture() as log:
            await self._test_process_seeds(process_seeds, [ITEM_A])

        assert "in process_seeds\n    raise RuntimeError" in str(log), log
