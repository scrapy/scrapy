import asyncio
import sys

from twisted.internet import asyncioreactor
if sys.version_info >= (3, 8) and sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncioreactor.install(asyncio.get_event_loop())

import scrapy
from scrapy.crawler import CrawlerProcess


class NoRequestsSpider(scrapy.Spider):
    name = 'no_request'

    def start_requests(self):
        return []


process = CrawlerProcess(settings={
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
})
process.crawl(NoRequestsSpider)
process.start()
