import scrapy
from scrapy.crawler import CrawlerProcess


class NoRequestsSpider(scrapy.Spider):
    name = 'no_request'

    def start_requests(self):
        return []


process = CrawlerProcess(settings={
    'ASYNCIO_ENABLED': True,
})

process.crawl(NoRequestsSpider)
process.start()
