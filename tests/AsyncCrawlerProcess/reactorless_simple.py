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
        # Pinned to silence the CONCURRENT_REQUESTS_PER_DOMAIN transition warning.
        "THROTTLING_SCOPE_CONCURRENCY": 1,
    }
)

process.crawl(NoRequestsSpider)
process.start()
