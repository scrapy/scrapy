import asyncio

from scrapy import Spider
from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.log import configure_logging


class NoRequestsSpider(Spider):
    name = "no_request"

    async def start(self):
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
            "TELNETCONSOLE_ENABLED": False,
        }
    )
    await runner.crawl(NoRequestsSpider)


asyncio.run(main())
