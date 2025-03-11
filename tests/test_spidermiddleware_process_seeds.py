from asyncio import sleep

import pytest
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase

from scrapy import Spider, signals
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from .test_spider_yield_seeds import ASYNC_GEN_ERROR_MINIMUM_SECONDS, twisted_sleep


class AsyncioSpiderMiddleware:
    async def process_seeds(self, seeds):
        await sleep(ASYNC_GEN_ERROR_MINIMUM_SECONDS)
        async for seed in seeds:
            yield seed


class NoOpSpiderMiddleware:
    async def process_seeds(self, seeds):
        async for seed in seeds:
            yield seed


class TwistedSpiderMiddleware:
    async def process_seeds(self, seeds):
        await maybe_deferred_to_future(twisted_sleep(ASYNC_GEN_ERROR_MINIMUM_SECONDS))
        async for seed in seeds:
            yield seed


class MainTestCase(TestCase):
    @inlineCallbacks
    def _test(self, spider_middlewares):
        item = {"a": "b"}

        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                yield item

        actual_items = []

        def track_item(item, response, spider):
            actual_items.append(item)

        settings = {
            "SPIDER_MIDDLEWARES": {cls: n for n, cls in enumerate(spider_middlewares)},
        }
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_item, signals.item_scraped)
        yield crawler.crawl()
        assert crawler.stats.get_value("finish_reason") == "finished"
        assert actual_items == [item]

    @pytest.mark.only_asyncio
    @inlineCallbacks
    def test_asyncio_delayed_single(self):
        yield self._test([AsyncioSpiderMiddleware])

    @pytest.mark.only_asyncio
    @inlineCallbacks
    def test_asyncio_delayed_multiple(self):
        yield self._test(
            [NoOpSpiderMiddleware, AsyncioSpiderMiddleware, NoOpSpiderMiddleware]
        )

    @inlineCallbacks
    def test_twisted_delayed_single(self):
        yield self._test([TwistedSpiderMiddleware])

    @inlineCallbacks
    def test_twisted_delayed_multiple(self):
        yield self._test(
            [NoOpSpiderMiddleware, TwistedSpiderMiddleware, NoOpSpiderMiddleware]
        )
