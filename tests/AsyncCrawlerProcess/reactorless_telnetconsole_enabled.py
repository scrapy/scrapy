import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = AsyncCrawlerProcess(
    settings={
        "TWISTED_ENABLED": False,
        "TELNETCONSOLE_ENABLED": True,
    }
)

process.crawl(NoRequestsSpider)
process.start()
