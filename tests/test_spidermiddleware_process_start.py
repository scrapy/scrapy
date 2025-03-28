import re
import warnings
from asyncio import sleep
from logging import ERROR

import pytest
from testfixtures import LogCapture
from twisted.trial.unittest import TestCase

from scrapy import Spider, signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from .test_spider_start import SLEEP_SECONDS, twisted_sleep

ITEM_A = {"id": "a"}
ITEM_B = {"id": "b"}
ITEM_C = {"id": "c"}
ITEM_D = {"id": "d"}


class AsyncioSleepSpiderMiddleware:
    async def process_start(self, start):
        await sleep(SLEEP_SECONDS)
        async for item_or_request in start:
            yield item_or_request


class NoOpSpiderMiddleware:
    async def process_start(self, start):
        async for item_or_request in start:
            yield item_or_request


class TwistedSleepSpiderMiddleware:
    async def process_start(self, start):
        await maybe_deferred_to_future(twisted_sleep(SLEEP_SECONDS))
        async for item_or_request in start:
            yield item_or_request


class UniversalSpiderMiddleware:
    async def process_start(self, start):
        async for item_or_request in start:
            yield item_or_request

    def process_start_requests(self, start_requests, spider):
        raise NotImplementedError


# Spiders and spider middlewares for MainTestCase._test_wrap


class ModernWrapSpider(Spider):
    name = "test"

    async def start(self):
        yield ITEM_B


class ModernWrapSpiderSubclass(ModernWrapSpider):
    name = "test"


class UniversalWrapSpider(Spider):
    name = "test"

    async def start(self):
        yield ITEM_B

    def start_requests(self):
        yield ITEM_D


class DeprecatedWrapSpider(Spider):
    name = "test"

    def start_requests(self):
        yield ITEM_B


class ModernWrapSpiderMiddleware:
    async def process_start(self, start):
        yield ITEM_A
        async for item_or_request in start:
            yield item_or_request
        yield ITEM_C


class UniversalWrapSpiderMiddleware:
    async def process_start(self, start):
        yield ITEM_A
        async for item_or_request in start:
            yield item_or_request
        yield ITEM_C

    def process_start_requests(self, start, spider):
        yield ITEM_A
        yield from start
        yield ITEM_C


class DeprecatedWrapSpiderMiddleware:
    def process_start_requests(self, start, spider):
        yield ITEM_A
        yield from start
        yield ITEM_C


class MainTestCase(TestCase):
    # Helper methods.

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

    async def _test_wrap(self, spider_middleware, spider_cls, expected_items=None):
        expected_items = (
            expected_items if expected_items is not None else [ITEM_A, ITEM_B, ITEM_C]
        )
        await self._test([spider_middleware], spider_cls, expected_items)

    async def _test_douple_wrap(self, smw1, smw2, spider_cls, expected_items=None):
        expected_items = (
            expected_items
            if expected_items is not None
            else [ITEM_A, ITEM_A, ITEM_B, ITEM_C, ITEM_C]
        )
        await self._test([smw1, smw2], spider_cls, expected_items)

    async def _test_process_start(self, process_start_fn, expected_items=None):
        class TestSpiderMiddleware:
            process_start = process_start_fn

        class TestSpider(Spider):
            name = "test"

        await self._test([TestSpiderMiddleware], TestSpider, expected_items)

    # Deprecation and universal.

    @deferred_f_from_coro_f
    async def test_modern_mw_modern_spider(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_wrap(ModernWrapSpiderMiddleware, ModernWrapSpider)

    @deferred_f_from_coro_f
    async def test_modern_mw_universal_spider(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_wrap(ModernWrapSpiderMiddleware, UniversalWrapSpider)

    @deferred_f_from_coro_f
    async def test_modern_mw_deprecated_spider(self):
        with pytest.warns(
            ScrapyDeprecationWarning, match=r"deprecated start_requests\(\)"
        ):
            await self._test_wrap(ModernWrapSpiderMiddleware, DeprecatedWrapSpider)

    @deferred_f_from_coro_f
    async def test_universal_mw_modern_spider(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_wrap(UniversalWrapSpiderMiddleware, ModernWrapSpider)

    @deferred_f_from_coro_f
    async def test_universal_mw_universal_spider(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
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
            pytest.warns(
                ScrapyDeprecationWarning, match=r"deprecated process_start_requests\(\)"
            ),
            LogCapture(level=ERROR) as log,
        ):
            await self._test_wrap(DeprecatedWrapSpiderMiddleware, ModernWrapSpider, [])
        assert "To solve this issue" in str(log), log

    @deferred_f_from_coro_f
    async def test_deprecated_mw_modern_spider_subclass(self):
        with (
            pytest.warns(
                ScrapyDeprecationWarning, match=r"deprecated process_start_requests\(\)"
            ),
            LogCapture(level=ERROR) as log,
        ):
            await self._test_wrap(
                DeprecatedWrapSpiderMiddleware, ModernWrapSpiderSubclass, []
            )
        assert re.search(
            r"\S+?\.ModernWrapSpider \(inherited by \S+?.ModernWrapSpiderSubclass\) .*? only compatible with \(deprecated\) spiders",
            str(log),
        ), log

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

    @deferred_f_from_coro_f
    async def test_modern_mw_universal_mw_modern_spider(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_douple_wrap(
                ModernWrapSpiderMiddleware,
                UniversalWrapSpiderMiddleware,
                ModernWrapSpider,
            )

    @deferred_f_from_coro_f
    async def test_modern_mw_deprecated_mw_modern_spider(self):
        with pytest.raises(ValueError, match=r"trying to combine spider middlewares"):
            await self._test_douple_wrap(
                ModernWrapSpiderMiddleware,
                DeprecatedWrapSpiderMiddleware,
                ModernWrapSpider,
            )

    @deferred_f_from_coro_f
    async def test_universal_mw_deprecated_mw_modern_spider(self):
        with (
            pytest.warns(
                ScrapyDeprecationWarning, match=r"deprecated process_start_requests\(\)"
            ),
            LogCapture(level=ERROR) as log,
        ):
            await self._test_douple_wrap(
                UniversalWrapSpiderMiddleware,
                DeprecatedWrapSpiderMiddleware,
                ModernWrapSpider,
                [],
            )
        assert re.search(r"only compatible with \(deprecated\) spiders", str(log)), log

    @deferred_f_from_coro_f
    async def test_modern_mw_universal_mw_universal_spider(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_douple_wrap(
                ModernWrapSpiderMiddleware,
                UniversalWrapSpiderMiddleware,
                UniversalWrapSpider,
            )

    @deferred_f_from_coro_f
    async def test_modern_mw_deprecated_mw_universal_spider(self):
        with pytest.raises(ValueError, match=r"trying to combine spider middlewares"):
            await self._test_douple_wrap(
                ModernWrapSpiderMiddleware,
                DeprecatedWrapSpiderMiddleware,
                UniversalWrapSpider,
            )

    @deferred_f_from_coro_f
    async def test_universal_mw_deprecated_mw_universal_spider(self):
        with pytest.warns(
            ScrapyDeprecationWarning, match=r"deprecated process_start_requests\(\)"
        ):
            await self._test_douple_wrap(
                UniversalWrapSpiderMiddleware,
                DeprecatedWrapSpiderMiddleware,
                UniversalWrapSpider,
                [ITEM_A, ITEM_A, ITEM_D, ITEM_C, ITEM_C],
            )

    @deferred_f_from_coro_f
    async def test_modern_mw_universal_mw_deprecated_spider(self):
        with pytest.warns(
            ScrapyDeprecationWarning, match=r"deprecated start_requests\(\)"
        ):
            await self._test_douple_wrap(
                ModernWrapSpiderMiddleware,
                UniversalWrapSpiderMiddleware,
                DeprecatedWrapSpider,
            )

    @deferred_f_from_coro_f
    async def test_modern_mw_deprecated_mw_deprecated_spider(self):
        with pytest.raises(ValueError, match=r"trying to combine spider middlewares"):
            await self._test_douple_wrap(
                ModernWrapSpiderMiddleware,
                DeprecatedWrapSpiderMiddleware,
                DeprecatedWrapSpider,
            )

    @deferred_f_from_coro_f
    async def test_universal_mw_deprecated_mw_deprecated_spider(self):
        with (
            pytest.warns(
                ScrapyDeprecationWarning, match=r"deprecated process_start_requests\(\)"
            ),
            pytest.warns(
                ScrapyDeprecationWarning, match=r"deprecated start_requests\(\)"
            ),
        ):
            await self._test_douple_wrap(
                UniversalWrapSpiderMiddleware,
                DeprecatedWrapSpiderMiddleware,
                DeprecatedWrapSpider,
            )

    # Bad definitions.

    @deferred_f_from_coro_f
    async def test_async_function(self):
        async def process_start(mw, seeds):
            return

        with LogCapture() as log:
            await self._test_process_start(process_start, [])

        assert ".process_start must be an asynchronous generator" in str(log), log

    @deferred_f_from_coro_f
    async def test_sync_function(self):
        def process_start(mw, spider):
            return []

        with LogCapture() as log:
            await self._test_process_start(process_start, [])

        assert ".process_start must be an asynchronous generator" in str(log)

    @deferred_f_from_coro_f
    async def test_sync_generator(self):
        def process_start(mw, spider):
            return
            yield

        with LogCapture() as log:
            await self._test_process_start(process_start, [])

        assert ".process_start must be an asynchronous generator" in str(log)

    # Exceptions during iteration.

    @deferred_f_from_coro_f
    async def test_exception_before_yield(self):
        async def process_start(mw, seeds):
            raise RuntimeError
            yield  # pylint: disable=unreachable

        with LogCapture() as log:
            await self._test_process_start(process_start, [])

        assert "in process_start\n    raise RuntimeError" in str(log), log

    @deferred_f_from_coro_f
    async def test_exception_after_yield(self):
        async def process_start(mw, spider):
            yield ITEM_A
            raise RuntimeError

        with LogCapture() as log:
            await self._test_process_start(process_start, [ITEM_A])

        assert "in process_start\n    raise RuntimeError" in str(log), log
