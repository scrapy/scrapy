import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class IPv6Spider(scrapy.Spider):
    """
    Raises a scrapy.exceptions.CannotResolveHostError:
    the default name resolver does not handle IPv6 addresses.
    """

    name = "ipv6_spider"

    async def start(self):
        # w3lib older than 2.4.1 strips the brackets, making the URL invalid.
        yield scrapy.Request("http://[::1]", meta={"verbatim_url": True})


if __name__ == "__main__":
    process = AsyncCrawlerProcess(settings={"RETRY_ENABLED": False})
    process.crawl(IPv6Spider)
    process.start()
