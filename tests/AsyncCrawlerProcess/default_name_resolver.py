import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class IPv6Spider(scrapy.Spider):
    """
    Raises a scrapy.exceptions.CannotResolveHostError:
    the default name resolver does not handle IPv6 addresses.
    """

    name = "ipv6_spider"
    start_urls = ["http://[::1]"]


if __name__ == "__main__":
    process = AsyncCrawlerProcess(settings={"RETRY_ENABLED": False})
    process.crawl(IPv6Spider)
    process.start()
