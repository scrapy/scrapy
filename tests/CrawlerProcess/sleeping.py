from twisted.internet.defer import Deferred

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.defer import maybe_deferred_to_future


class SleepingSpider(scrapy.Spider):
    name = "sleeping"

    start_urls = ["data:,;"]

    async def parse(self, response):
        from twisted.internet import reactor

        d = Deferred()
        reactor.callLater(int(self.sleep), d.callback, None)
        await maybe_deferred_to_future(d)


process = CrawlerProcess(settings={})

process.crawl(SleepingSpider)
process.start()
