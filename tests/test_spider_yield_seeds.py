from asyncio import sleep

import pytest
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.trial.unittest import TestCase

from scrapy import Spider, signals
from scrapy.core.engine import ExecutionEngine
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.test import get_crawler


class MainTestCase(TestCase):
    item = {"a": "b"}

    @inlineCallbacks
    def _test(self, yield_seeds_):
        class TestSpider(Spider):
            name = "test"
            yield_seeds = yield_seeds_

        actual_items = []

        def track_item(item, response, spider):
            actual_items.append(item)

        crawler = get_crawler(TestSpider)
        crawler.signals.connect(track_item, signals.item_scraped)
        yield crawler.crawl()
        assert crawler.stats.get_value("finish_reason") == "finished"
        assert actual_items == [self.item]

    @pytest.mark.only_asyncio
    @inlineCallbacks
    def test_asyncio_delayed(self):
        async def yield_seeds(spider):
            await sleep(ExecutionEngine._SLOT_HEARTBEAT_INTERVAL + 0.01)
            yield self.item

        yield self._test(yield_seeds)

    @inlineCallbacks
    def test_twisted_delayed(self):
        def twisted_sleep(seconds):
            from twisted.internet import reactor

            d = Deferred()
            reactor.callLater(seconds, d.callback, None)
            return d

        async def yield_seeds(spider):
            await maybe_deferred_to_future(
                twisted_sleep(ExecutionEngine._SLOT_HEARTBEAT_INTERVAL + 0.01)
            )
            yield self.item

        yield self._test(yield_seeds)
