import asyncio

from scrapy import Spider
from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.log import configure_logging
from scrapy.utils.reactorless import is_reactorless
from tests.utils import CURRENT_DEFAULTS


class NoRequestsSpider(Spider):
    name = "no_request"

    async def start(self):
        self.logger.info(f"is_reactorless(): {is_reactorless()}")
        return
        yield


async def main() -> None:
    configure_logging()
    runner = AsyncCrawlerRunner(
        settings={
            "TWISTED_REACTOR_ENABLED": False,
            "MEMUSAGE_ENABLED": False,
            **CURRENT_DEFAULTS,
        }
    )
    await runner.crawl(NoRequestsSpider)


asyncio.run(main())
