from __future__ import annotations

import asyncio
import sys

from scrapy import Spider
from scrapy.crawler import AsyncCrawlerProcess


class ItemsSpider(Spider):
    """Yields an item every 0.1 seconds for 3 seconds, so the spider must not
    be closed by CLOSESPIDER_TIMEOUT_NO_ITEM = 1."""

    name = "items"

    async def start(self):
        for i in range(30):
            await asyncio.sleep(0.1)
            yield {"i": i}


if __name__ == "__main__":
    ASYNCIO_EVENT_LOOP: str | None
    try:
        ASYNCIO_EVENT_LOOP = sys.argv[1]
    except IndexError:
        ASYNCIO_EVENT_LOOP = None

    process = AsyncCrawlerProcess(
        settings={
            "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
            "ASYNCIO_EVENT_LOOP": ASYNCIO_EVENT_LOOP,
            "CLOSESPIDER_TIMEOUT_NO_ITEM": 1,
        }
    )
    process.crawl(ItemsSpider)
    process.start()
