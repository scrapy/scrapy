import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process1 = AsyncCrawlerProcess(settings={"TWISTED_REACTOR_ENABLED": False})
process2 = AsyncCrawlerProcess(settings={"TWISTED_REACTOR_ENABLED": False})
process1.crawl(NoRequestsSpider)
process2.crawl(NoRequestsSpider)
process1.start()
process2.start()
