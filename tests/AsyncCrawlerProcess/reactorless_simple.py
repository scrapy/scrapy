import scrapy
from scrapy.crawler import AsyncCrawlerProcess
from scrapy.utils.reactorless import is_reactorless


class AsyncioCheckExtension:
    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.asyncio_enabled:
            raise RuntimeError("Crawler did not report asyncio support.")
        return cls()


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        self.logger.info(f"is_reactorless(): {is_reactorless()}")
        return
        yield


process = AsyncCrawlerProcess(
    settings={
        "TWISTED_REACTOR_ENABLED": False,
        "EXTENSIONS": {AsyncioCheckExtension: 0},
    }
)

process.crawl(NoRequestsSpider)
process.start()
