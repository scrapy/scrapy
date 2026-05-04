import warnings
from asyncio import sleep

import pytest

from scrapy import Spider, signals
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.test_spider_start import SLEEP_SECONDS

from .utils import twisted_sleep
from .utils.decorators import coroutine_test

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


# Spiders and spider middlewares for TestMain._test_wrap


class ModernWrapSpider(Spider):
    name = "test"

    async def start(self):
        yield ITEM_B


class ModernWrapSpiderSubclass(ModernWrapSpider):
    name = "test"


class ModernWrapSpiderMiddleware:
    async def process_start(self, start):
        yield ITEM_A
        async for item_or_request in start:
            yield item_or_request
        yield ITEM_C


class TestMain:
    async def _test(self, spider_middlewares, spider_cls, expected_items):
        actual_items = []

        def track_item(item, response, spider):
            actual_items.append(item)

        settings = {
            "SPIDER_MIDDLEWARES": {cls: n for n, cls in enumerate(spider_middlewares)},
        }
        crawler = get_crawler(spider_cls, settings_dict=settings)
        crawler.signals.connect(track_item, signals.item_scraped)
        await crawler.crawl_async()
        assert crawler.stats.get_value("finish_reason") == "finished"
        assert actual_items == expected_items, f"{actual_items=} != {expected_items=}"

    async def _test_wrap(self, spider_middleware, spider_cls, expected_items=None):
        expected_items = expected_items or [ITEM_A, ITEM_B, ITEM_C]
        await self._test([spider_middleware], spider_cls, expected_items)

    async def _test_douple_wrap(self, smw1, smw2, spider_cls, expected_items=None):
        expected_items = expected_items or [ITEM_A, ITEM_A, ITEM_B, ITEM_C, ITEM_C]
        await self._test([smw1, smw2], spider_cls, expected_items)

    @coroutine_test
    async def test_modern_mw_modern_spider(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_wrap(ModernWrapSpiderMiddleware, ModernWrapSpider)

    async def _test_sleep(self, spider_middlewares):
        class TestSpider(Spider):
            name = "test"

            async def start(self):
                yield ITEM_A

        await self._test(spider_middlewares, TestSpider, [ITEM_A])

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_asyncio_sleep_single(self):
        await self._test_sleep([AsyncioSleepSpiderMiddleware])

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_asyncio_sleep_multiple(self):
        await self._test_sleep(
            [NoOpSpiderMiddleware, AsyncioSleepSpiderMiddleware, NoOpSpiderMiddleware]
        )

    @pytest.mark.requires_reactor  # needs a reactor for twisted_sleep()
    @coroutine_test
    async def test_twisted_sleep_single(self):
        await self._test_sleep([TwistedSleepSpiderMiddleware])

    @pytest.mark.requires_reactor  # needs a reactor for twisted_sleep()
    @coroutine_test
    async def test_twisted_sleep_multiple(self):
        await self._test_sleep(
            [NoOpSpiderMiddleware, TwistedSleepSpiderMiddleware, NoOpSpiderMiddleware]
        )
