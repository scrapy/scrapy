import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class AsyncioReactorSpider(scrapy.Spider):
    name = "asyncio_reactor"


process = AsyncCrawlerProcess(
    settings={
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    }
)
process.crawl(AsyncioReactorSpider)
process.start()
