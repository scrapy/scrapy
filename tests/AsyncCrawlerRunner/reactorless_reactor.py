import asyncio

from scrapy import Spider
from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.log import configure_logging
from scrapy.utils.reactor import install_reactor


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
        }
    )
    await runner.crawl(NoRequestsSpider)


install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
asyncio.run(main())
