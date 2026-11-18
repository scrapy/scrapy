import asyncio
import logging

import scrapy
from scrapy.crawler import AsyncCrawlerProcess

logger = logging.getLogger(__name__)


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        self.logger.info(
            f"Running in the current loop: {asyncio.get_running_loop() is loop}"
        )
        return
        yield


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
process = AsyncCrawlerProcess(settings={"TWISTED_REACTOR_ENABLED": False})
process.crawl(NoRequestsSpider)
process.start()
logger.info(f"Current loop kept: {asyncio.get_event_loop() is loop}")
logger.info(f"Current loop closed: {loop.is_closed()}")
loop.close()
