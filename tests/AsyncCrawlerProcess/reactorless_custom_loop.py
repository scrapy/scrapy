import asyncio

import scrapy
from scrapy.crawler import AsyncCrawlerProcess
from scrapy.utils.python import global_object_name


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        loop_class = type(asyncio.get_running_loop())
        self.logger.info(f"Running loop: {global_object_name(loop_class)}")
        return
        yield


process = AsyncCrawlerProcess(
    settings={"TWISTED_REACTOR_ENABLED": False, "ASYNCIO_EVENT_LOOP": "uvloop.Loop"}
)
process.crawl(NoRequestsSpider)
process.start()
