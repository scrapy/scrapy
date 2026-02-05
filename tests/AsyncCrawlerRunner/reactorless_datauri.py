import asyncio

from scrapy import Request, Spider
from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.log import configure_logging


class DataSpider(Spider):
    name = "data"

    async def start(self):
        yield Request("data:,foo")

    def parse(self, response):
        return {"data": response.text}


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
    await runner.crawl(DataSpider)


asyncio.run(main())
