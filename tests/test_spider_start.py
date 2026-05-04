from __future__ import annotations

import warnings
from asyncio import sleep
from typing import Any

import pytest

from scrapy import Spider, signals
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from .utils import twisted_sleep
from .utils.decorators import coroutine_test

SLEEP_SECONDS = 0.1

ITEM_A = {"id": "a"}
ITEM_B = {"id": "b"}


class TestMain:
    async def _test_spider(
        self, spider: type[Spider], expected_items: list[Any] | None = None
    ) -> None:
        actual_items = []
        expected_items = [] if expected_items is None else expected_items

        def track_item(item, response, spider):
            actual_items.append(item)

        crawler = get_crawler(spider)
        crawler.signals.connect(track_item, signals.item_scraped)
        await crawler.crawl_async()
        assert crawler.stats
        assert crawler.stats.get_value("finish_reason") == "finished"
        assert actual_items == expected_items

    @coroutine_test
    async def test_start_urls(self):
        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]

            async def parse(self, response):
                yield ITEM_A

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_spider(TestSpider, [ITEM_A])

    @coroutine_test
    async def test_start(self):
        class TestSpider(Spider):
            name = "test"

            async def start(self):
                yield ITEM_A

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_spider(TestSpider, [ITEM_A])

    @coroutine_test
    async def test_start_subclass(self):
        class BaseSpider(Spider):
            async def start(self):
                yield ITEM_A

        class TestSpider(BaseSpider):
            name = "test"

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await self._test_spider(TestSpider, [ITEM_A])

    async def _test_start(self, start_, expected_items=None):
        class TestSpider(Spider):
            name = "test"
            start = start_

        await self._test_spider(TestSpider, expected_items)

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_asyncio_delayed(self):
        async def start(spider):
            await sleep(SLEEP_SECONDS)
            yield ITEM_A

        await self._test_start(start, [ITEM_A])

    @pytest.mark.requires_reactor  # needs a reactor for twisted_sleep()
    @coroutine_test
    async def test_twisted_delayed(self):
        async def start(spider):
            await maybe_deferred_to_future(twisted_sleep(SLEEP_SECONDS))
            yield ITEM_A

        await self._test_start(start, [ITEM_A])
