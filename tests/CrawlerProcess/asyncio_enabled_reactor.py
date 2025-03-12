import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.reactor import install_reactor

install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def yield_seeds(self):
        return
        yield


process = CrawlerProcess(
    settings={
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    }
)
process.crawl(NoRequestsSpider)
process.start()
