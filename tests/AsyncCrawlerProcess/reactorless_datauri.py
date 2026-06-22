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
        "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
        "DOWNLOAD_DELAY": 0,
        "ROBOTSTXT_OBEY": False,
    }
)

process.crawl(DataSpider)
process.start()
