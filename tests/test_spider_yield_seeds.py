from asyncio import sleep

import pytest
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.trial.unittest import TestCase

from scrapy import Spider, signals
from scrapy.core.engine import ExecutionEngine
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.test import get_crawler


class MainTestCase(TestCase):
    @inlineCallbacks
    def _test_scenario(self, scenario):
        class TestSpider(Spider):
            name = "test"
            yield_seeds = scenario.yield_seeds

        actual_items = []

        def track_item(item, response, spider):
            actual_items.append(item)

        crawler = get_crawler(TestSpider)
        crawler.signals.connect(track_item, signals.item_scraped)
        yield crawler.crawl()
        assert crawler.stats.get_value("finish_reason") == "finished"
        assert actual_items == scenario.expected_items

    @pytest.mark.only_asyncio
    @inlineCallbacks
    def test_asyncio_delayed(self):
        class Scenario:
            expected_items = [{"a": "b"}]
            only_asyncio = True

            async def yield_seeds(self):
                await sleep(ExecutionEngine._SLOT_HEARTBEAT_INTERVAL + 0.01)
                yield {"a": "b"}

        yield self._test_scenario(Scenario)

    @inlineCallbacks
    def test_twisted_delayed(self):
        def twisted_sleep(seconds):
            d = Deferred()
            from twisted.internet import reactor

            reactor.callLater(seconds, d.callback, None)
            return d

        class Scenario:
            expected_items = [{"a": "b"}]
            only_asyncio = True

            async def yield_seeds(self):
                await maybe_deferred_to_future(
                    twisted_sleep(ExecutionEngine._SLOT_HEARTBEAT_INTERVAL + 0.01)
                )
                yield {"a": "b"}

        yield self._test_scenario(Scenario)
