from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar

from scrapy import Spider
from scrapy.core.scraper import Scraper
from scrapy.utils.test import get_crawler
from tests.spiders import SimpleSpider
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    import pytest

    from tests.mockserver.http import MockServer


@coroutine_test
async def test_scraper_exception(
    mockserver: MockServer,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crawler = get_crawler(SimpleSpider)
    monkeypatch.setattr(
        "scrapy.core.engine.Scraper.handle_spider_output_async",
        lambda *args, **kwargs: 1 / 0,
    )
    await crawler.crawl_async(url=mockserver.url("/"))
    assert "Scraper bug processing" in caplog.text


@coroutine_test
async def test_close_spider_async_waits_for_item_processing() -> None:
    process_started = asyncio.Event()
    finish_processing = asyncio.Event()

    class BlockingPipeline:
        events: ClassVar[list[str]] = []

        async def process_item(self, item: Any) -> Any:
            self.events.append("process_item_start")
            process_started.set()
            await finish_processing.wait()
            self.events.append("process_item_end")
            return item

        async def close_spider(self) -> None:
            self.events.append("close_spider")

    class TestSpider(Spider):
        name = "test"

    crawler = get_crawler(
        TestSpider,
        {
            "ITEM_PIPELINES": {
                BlockingPipeline: 0,
            },
        },
    )
    crawler.spider = crawler._create_spider()
    scraper = Scraper(crawler)
    await scraper.open_spider_async()

    itemproc_task = asyncio.create_task(scraper.start_itemproc_async({}, response=None))
    await process_started.wait()

    close_task = asyncio.create_task(scraper.close_spider_async())
    try:
        await asyncio.sleep(0)
        assert not close_task.done()
        assert BlockingPipeline.events == ["process_item_start"]
    finally:
        finish_processing.set()
        await itemproc_task
        await close_task

    assert BlockingPipeline.events == [
        "process_item_start",
        "process_item_end",
        "close_spider",
    ]
