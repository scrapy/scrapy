import asyncio

from scrapy import Spider
from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.log import configure_logging


class NoRequestsSpider(Spider):
    name = "no_request"

    async def start(self):
        return
        yield


async def main() -> None:
    configure_logging()
    runner = AsyncCrawlerRunner()
    await runner.crawl(NoRequestsSpider)


asyncio.run(main())
