import sys

import scrapy


class ItemSpider(scrapy.Spider):
    name = "items"

    async def start(self):
        for index in range(3):
            yield {"index": index}


crawl = scrapy.run(ItemSpider, items=True)
for item in crawl:
    print(f"item: {item['index']}", file=sys.stderr)
print(
    f"item_scraped_count: {crawl.crawler.stats.get_value('item_scraped_count')}",
    file=sys.stderr,
)
