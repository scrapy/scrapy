import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class AsyncioReactorSpider1(scrapy.Spider):
    name = "asyncio_reactor1"
    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    }


class AsyncioReactorSpider2(scrapy.Spider):
    name = "asyncio_reactor2"
    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    }


process = AsyncCrawlerProcess()
process.crawl(AsyncioReactorSpider1)
process.crawl(AsyncioReactorSpider2)
process.start()
