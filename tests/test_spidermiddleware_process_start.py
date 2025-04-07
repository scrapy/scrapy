import warnings
from asyncio import sleep

import pytest
from twisted.trial.unittest import TestCase

from scrapy import Spider, signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.test_spider_start import SLEEP_SECONDS

from .utils import twisted_sleep

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
        expected_items = expected_items or [ITEM_A, ITEM_B, ITEM_C]
        await self._test([spider_middleware], spider_cls, expected_items)

    async def _test_douple_wrap(self, smw1, smw2, spider_cls, expected_items=None):
        expected_items = expected_items or [ITEM_A, ITEM_A, ITEM_B, ITEM_C, ITEM_C]
        await self._test([smw1, smw2], spider_cls, expected_items)

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
            pytest.raises(
                ValueError, match=r"only compatible with \(deprecated\) spiders"
            ),
        ):
            await self._test_wrap(DeprecatedWrapSpiderMiddleware, ModernWrapSpider)

    @deferred_f_from_coro_f
    async def test_deprecated_mw_modern_spider_subclass(self):
        with (
            pytest.warns(
                ScrapyDeprecationWarning, match=r"deprecated process_start_requests\(\)"
            ),
            pytest.raises(
                ValueError,
                match=r"^\S+?\.ModernWrapSpider \(inherited by \S+?.ModernWrapSpiderSubclass\) .*? only compatible with \(deprecated\) spiders",
            ),
        ):
            await self._test_wrap(
                DeprecatedWrapSpiderMiddleware, ModernWrapSpiderSubclass
            )

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
            pytest.raises(
                ValueError, match=r"only compatible with \(deprecated\) spiders"
            ),
        ):
            await self._test_douple_wrap(
                UniversalWrapSpiderMiddleware,
                DeprecatedWrapSpiderMiddleware,
                ModernWrapSpider,
            )

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

    async def _test_sleep(self, spider_middlewares):
        class TestSpider(Spider):
            name = "test"

            async def start(self):
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
