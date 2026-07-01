import scrapy
from scrapy.crawler import CrawlerProcess


class AsyncioReactorSpider(scrapy.Spider):
    name = "asyncio_reactor"
    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    }


process = CrawlerProcess()
process.crawl(AsyncioReactorSpider)
process.start()
