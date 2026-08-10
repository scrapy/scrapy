import scrapy
from scrapy.crawler import AsyncCrawlerProcess
from scrapy.utils.reactor import is_asyncio_reactor_installed


class ReactorCheckExtension:
    @classmethod
    def from_crawler(cls, crawler):
        if not is_asyncio_reactor_installed():
            raise RuntimeError("ReactorCheckExtension requires the asyncio reactor.")
        if not crawler.asyncio_enabled:
            raise RuntimeError("Crawler did not report asyncio support.")
        return cls()


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = AsyncCrawlerProcess(
    settings={
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "EXTENSIONS": {ReactorCheckExtension: 0},
    }
)
process.crawl(NoRequestsSpider)
process.start()
