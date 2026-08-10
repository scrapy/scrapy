from twisted.internet import selectreactor
from twisted.python import log

import scrapy
from scrapy.crawler import CrawlerProcess

selectreactor.install()


class AsyncioCheckExtension:
    @classmethod
    def from_crawler(cls, crawler):
        if crawler.asyncio_enabled:
            raise RuntimeError("Crawler unexpectedly reported asyncio support.")
        return cls()


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = CrawlerProcess(settings={"EXTENSIONS": {AsyncioCheckExtension: 0}})

d = process.crawl(NoRequestsSpider)
d.addErrback(log.err)
process.start()
