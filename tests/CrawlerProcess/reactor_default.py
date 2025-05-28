from twisted.internet import reactor  # noqa: F401,TID253
from twisted.python import log

import scrapy
from scrapy.crawler import CrawlerProcess


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = CrawlerProcess(settings={})

d = process.crawl(NoRequestsSpider)
d.addErrback(log.err)
process.start()
