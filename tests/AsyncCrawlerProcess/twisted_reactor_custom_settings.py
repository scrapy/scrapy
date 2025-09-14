import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class AsyncioReactorSpider(scrapy.Spider):
    name = "asyncio_reactor"
    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    }


process = AsyncCrawlerProcess()
process.crawl(AsyncioReactorSpider)
process.start()
