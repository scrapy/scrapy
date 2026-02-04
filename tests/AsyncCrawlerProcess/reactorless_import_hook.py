import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        import twisted.internet.reactor  # noqa: F401

        return
        yield


process = AsyncCrawlerProcess(
    settings={
        "TWISTED_ENABLED": False,
        "DOWNLOAD_HANDLERS": {
            "http": None,
            "https": None,
            "ftp": None,
        },
    }
)

process.crawl(NoRequestsSpider)
process.start()
