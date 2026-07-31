from twisted.internet import reactor  # noqa: F401,TID253

import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = AsyncCrawlerProcess(settings={})

d = process.crawl(NoRequestsSpider)
process.start()
