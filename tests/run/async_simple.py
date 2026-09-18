import asyncio
import sys

import scrapy
from scrapy.utils.reactorless import is_reactorless


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        self.logger.info(f"is_reactorless(): {is_reactorless()}")
        return
        yield


async def main() -> None:
    crawler = await scrapy.run_async(NoRequestsSpider)
    assert crawler.spider is not None
    print(f"spider: {crawler.spider.name}", file=sys.stderr)
    print(f"finish_reason: {crawler.stats.get_value('finish_reason')}", file=sys.stderr)


asyncio.run(main())
