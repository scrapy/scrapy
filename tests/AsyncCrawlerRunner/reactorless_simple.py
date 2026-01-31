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


async def main():
    configure_logging()
    runner = AsyncCrawlerRunner(
        settings={
            "TWISTED_ENABLED": False,
            "DOWNLOAD_HANDLERS": {
                "http": None,
                "https": None,
                "ftp": None,
            },
        }
    )
    await runner.crawl(NoRequestsSpider)


asyncio.run(main())
