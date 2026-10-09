from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Request, Spider, signals
from scrapy.utils.test import get_crawler, get_from_asyncio_queue
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from tests.mockserver.http import MockServer


class ItemSpider(Spider):
    name = "itemspider"
    mockserver: MockServer

    async def start(self):
        for index in range(10):
            yield Request(
                self.mockserver.url(f"/status?n=200&id={index}"), meta={"index": index}
            )

    def parse(self, response):
        return {"index": response.meta["index"]}


@coroutine_test
async def test_scheduler_empty() -> None:
    crawler = get_crawler()
    calls = []

    def track_call() -> None:
        calls.append(object())

    crawler.signals.connect(track_call, signals.scheduler_empty)
    await crawler.crawl_async()
    assert len(calls) >= 1


@pytest.mark.only_asyncio
@coroutine_test
async def test_simple_pipeline(mockserver: MockServer) -> None:
    items: list[Any] = []

    async def _on_item_scraped(item: Any) -> None:
        item = await get_from_asyncio_queue(item)
        items.append(item)

    crawler = get_crawler(ItemSpider)
    crawler.signals.connect(_on_item_scraped, signals.item_scraped)
    await crawler.crawl_async(mockserver=mockserver)
    assert len(items) == 10
    for index in range(10):
        assert {"index": index} in items
