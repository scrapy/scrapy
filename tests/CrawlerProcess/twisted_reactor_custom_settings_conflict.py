import scrapy
from scrapy.crawler import CrawlerProcess


class PollReactorSpider(scrapy.Spider):
    name = 'poll_reactor'
    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.pollreactor.PollReactor",
    }


class AsyncioReactorSpider(scrapy.Spider):
    name = 'asyncio_reactor'
    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    }


process = CrawlerProcess()
process.crawl(PollReactorSpider)
process.crawl(AsyncioReactorSpider)
process.start()
