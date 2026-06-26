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


async def main() -> None:
    configure_logging()
    runner = AsyncCrawlerRunner(
        settings={
            "TWISTED_REACTOR_ENABLED": False,
            "COMPRESSION_KEEP_ENCODING_HEADER": True,
        }
    )
    await runner.crawl(DataSpider)


asyncio.run(main())
