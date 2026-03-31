import scrapy
from scrapy.crawler import AsyncCrawlerProcess
from scrapy.utils.reactorless import is_reactorless


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"
    custom_settings = {
        "TWISTED_ENABLED": False,
    }

    async def start(self):
        self.logger.info(f"is_reactorless(): {is_reactorless()}")
        return
        yield


process = AsyncCrawlerProcess()
process.crawl(NoRequestsSpider)
process.start()
