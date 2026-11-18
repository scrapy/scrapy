import asyncio
import logging

import scrapy
from scrapy.crawler import AsyncCrawlerProcess

logger = logging.getLogger(__name__)


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


async def main() -> AsyncCrawlerProcess:
    process = AsyncCrawlerProcess(settings={"TWISTED_REACTOR_ENABLED": False})
    process.crawl(NoRequestsSpider)
    try:
        process.start()
    except RuntimeError as e:
        logger.info(f"start() failed: {e}")
    await asyncio.sleep(0)
    logger.info("The running loop still works")
    return process


process = asyncio.run(main())
process.start()
