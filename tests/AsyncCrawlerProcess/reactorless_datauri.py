from scrapy import Request, Spider
from scrapy.crawler import AsyncCrawlerProcess


class DataSpider(Spider):
    name = "data"

    async def start(self):
        yield Request("data:,foo")

    def parse(self, response):
        return {"data": response.text}


process = AsyncCrawlerProcess(
    settings={
        "TWISTED_REACTOR_ENABLED": False,
        # Pinned to silence the CONCURRENT_REQUESTS_PER_DOMAIN transition warning.
        "THROTTLING_SCOPE_CONCURRENCY": 1,
    }
)

process.crawl(DataSpider)
process.start()
