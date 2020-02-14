import scrapy
from scrapy.crawler import CrawlerProcess


class AsyncioReactorSpider(scrapy.Spider):
    name = 'asyncio_reactor'


process = CrawlerProcess(settings={
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
})
process.crawl(AsyncioReactorSpider)
process.start()
