import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = AsyncCrawlerProcess(settings={"TWISTED_REACTOR_ENABLED": False})
process.crawl(NoRequestsSpider)
process.start()

process2 = AsyncCrawlerProcess()
process2.crawl(NoRequestsSpider)
process2.start()
