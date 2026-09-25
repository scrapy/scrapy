import scrapy
from scrapy.crawler import AsyncCrawlerProcess
from scrapy.utils.reactorless import is_reactorless


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        self.logger.info(f"is_reactorless(): {is_reactorless()}")
        return
        yield


process = AsyncCrawlerProcess(
    settings={
        "TWISTED_REACTOR_ENABLED": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
        "DOWNLOAD_DELAY": 0,
        "ROBOTSTXT_OBEY": False,
    }
)

process.crawl(NoRequestsSpider)
process.start()
