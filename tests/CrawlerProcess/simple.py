import scrapy
from scrapy.crawler import CrawlerProcess


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = CrawlerProcess(settings={})

process.crawl(NoRequestsSpider)
process.start()
