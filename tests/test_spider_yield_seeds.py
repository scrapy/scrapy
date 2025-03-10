from asyncio import sleep

import pytest
from pytest_twisted import ensureDeferred

from scrapy import Spider, signals
from scrapy.core.engine import ExecutionEngine
from scrapy.utils.test import get_crawler


class Scenario:
    pass


class AsyncioScenario(Scenario):
    expected_items = [{"a": "b"}]
    only_asyncio = True

    async def yield_seeds(self):
        await sleep(ExecutionEngine._SLOT_HEARTBEAT_INTERVAL + 0.01)
        yield {"a": "b"}


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(
            scenario,
            marks=pytest.mark.only_asyncio
            if getattr(scenario, "only_asyncio", False)
            else [],
        )
        for scenario in Scenario.__subclasses__()
    ],
)
@ensureDeferred
async def test_main(scenario):
    class TestSpider(Spider):
        name = "test"
        yield_seeds = scenario.yield_seeds

    actual_items = []

    def track_item(item, response, spider):
        actual_items.append(item)

    crawler = get_crawler(TestSpider)
    crawler.signals.connect(track_item, signals.item_scraped)
    await crawler.crawl()
    assert crawler.stats.get_value("finish_reason") == "finished"
    assert actual_items == scenario.expected_items
