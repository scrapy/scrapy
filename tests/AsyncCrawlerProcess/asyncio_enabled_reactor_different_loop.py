import asyncio
import sys

from twisted.internet import asyncioreactor

import scrapy
from scrapy.crawler import AsyncCrawlerProcess

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# Install the asyncio reactor with the default (non-uvloop) event loop, so it
# doesn't match the uvloop.Loop requested via the ASYNCIO_EVENT_LOOP setting.
asyncioreactor.install(asyncio.new_event_loop())


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = AsyncCrawlerProcess(
    settings={
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "ASYNCIO_EVENT_LOOP": "uvloop.Loop",
    }
)
process.crawl(NoRequestsSpider)
process.start()
