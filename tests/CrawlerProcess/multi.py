import scrapy
from scrapy.crawler import CrawlerProcess


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def yield_seeds(self):
        return
        yield


process = CrawlerProcess(settings={})

process.crawl(NoRequestsSpider)
process.crawl(NoRequestsSpider)
process.start()
