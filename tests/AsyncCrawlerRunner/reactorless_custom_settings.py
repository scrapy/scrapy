import asyncio

from scrapy import Spider
from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.log import configure_logging
from scrapy.utils.reactorless import is_reactorless


class NoRequestsSpider(Spider):
    name = "no_request"
    custom_settings = {
        "TWISTED_ENABLED": False,
    }

    async def start(self):
        self.logger.info(f"is_reactorless(): {is_reactorless()}")
        return
        yield


async def main() -> None:
    configure_logging()
    runner = AsyncCrawlerRunner()
    await runner.crawl(NoRequestsSpider)


asyncio.run(main())
