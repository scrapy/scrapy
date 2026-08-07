from twisted.python import log

import scrapy
from scrapy.crawler import CrawlerProcess


class SelectReactorSpider(scrapy.Spider):
    name = "select_reactor"
    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.selectreactor.SelectReactor",
    }


class AsyncioReactorSpider(scrapy.Spider):
    name = "asyncio_reactor"
    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    }


process = CrawlerProcess()
d1 = process.crawl(SelectReactorSpider)
d1.addErrback(log.err)
d2 = process.crawl(AsyncioReactorSpider)
d2.addErrback(log.err)
process.start()
