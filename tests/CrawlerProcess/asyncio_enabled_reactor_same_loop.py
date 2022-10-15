import asyncio
import sys

from uvloop import Loop

from twisted.internet import asyncioreactor
if sys.version_info >= (3, 8) and sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.set_event_loop(Loop())
asyncioreactor.install(asyncio.get_event_loop())

import scrapy  # noqa: E402
from scrapy.crawler import CrawlerProcess  # noqa: E402


class NoRequestsSpider(scrapy.Spider):
    name = 'no_request'

    def start_requests(self):
        return []


process = CrawlerProcess(settings={
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    "ASYNCIO_EVENT_LOOP": "uvloop.Loop",
})
process.crawl(NoRequestsSpider)
process.start()
