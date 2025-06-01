import asyncio
import sys

from twisted.internet import asyncioreactor
from uvloop import Loop

import scrapy
from scrapy.crawler import CrawlerProcess

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.set_event_loop(Loop())
asyncioreactor.install()


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = CrawlerProcess(
    settings={
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "ASYNCIO_EVENT_LOOP": "uvloop.Loop",
    }
)
process.crawl(NoRequestsSpider)
process.start()
