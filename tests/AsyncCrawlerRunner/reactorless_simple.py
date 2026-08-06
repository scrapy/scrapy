import asyncio

from scrapy import Spider
from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.log import configure_logging
from scrapy.utils.reactorless import is_reactorless


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
            # Pinned to silence the CONCURRENT_REQUESTS_PER_DOMAIN transition warning.
            "THROTTLING_SCOPE_CONCURRENCY": 1,
        }
    )
    await runner.crawl(NoRequestsSpider)


asyncio.run(main())
