import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.reactorless import is_reactorless


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        self.logger.info(f"is_reactorless(): {is_reactorless()}")
        return
        yield


process = CrawlerProcess(settings={})

process.crawl(NoRequestsSpider)
process.start()
