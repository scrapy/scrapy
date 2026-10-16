import asyncio

from scrapy import Spider
from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.log import configure_logging


class NoRequestsSpider(Spider):
    name = "no_request"

    async def start(self):
        return
        yield


configure_logging()
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
runner = AsyncCrawlerRunner(
    settings={"TWISTED_REACTOR_ENABLED": False, "MEMUSAGE_ENABLED": False}
)
runner.crawl(NoRequestsSpider)
loop.run_until_complete(runner.join())
