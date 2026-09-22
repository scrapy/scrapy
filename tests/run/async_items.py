import asyncio
import gc
import sys

import scrapy


class ItemSpider(scrapy.Spider):
    name = "items"
    item_count = 3

    async def start(self):
        for index in range(self.item_count):
            yield {"index": index}


async def main() -> None:
    crawl = scrapy.run_async(ItemSpider, items=True)
    async for item in crawl:
        print(f"item: {item['index']}", file=sys.stderr)
    assert await crawl is crawl
    assert crawl.items is not None
    print(f"items: {len(crawl.items)}", file=sys.stderr)
    print(
        f"item_scraped_count: {crawl.crawler.stats.get_value('item_scraped_count')}",
        file=sys.stderr,
    )

    try:
        async for _item in crawl:
            pass
    except RuntimeError as exception:
        print(f"RuntimeError: {exception}", file=sys.stderr)

    collected = await scrapy.run_async(ItemSpider, items=True)
    print(f"collected: {len(list(collected))}", file=sys.stderr)

    # Leaving a crawl in the middle stops it.
    partial = scrapy.run_async(ItemSpider, {"item_count": 50})
    items = partial.__aiter__()
    async for item in items:
        print(f"partial: {item['index']}", file=sys.stderr)
        break
    await items.aclose()
    print(
        f"partial_finish_reason: {partial.crawler.stats.get_value('finish_reason')}",
        file=sys.stderr,
    )

    scrapy.run_async(ItemSpider)
    gc.collect()


asyncio.run(main())
