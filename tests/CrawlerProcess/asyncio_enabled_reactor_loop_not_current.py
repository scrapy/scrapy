import asyncio

from twisted.internet import asyncioreactor

import scrapy
from scrapy.crawler import CrawlerProcess

# Twisted doesn't make a loop passed to it the current event loop.
asyncioreactor.install(asyncio.SelectorEventLoop())


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = CrawlerProcess()
process.crawl(NoRequestsSpider)
process.start()
