import scrapy
from scrapy.crawler import CrawlerProcess


class IPv6Spider(scrapy.Spider):
    """
    Raises a twisted.internet.error.DNSLookupError:
    the default name resolver does not handle IPv6 addresses.
    """
    name = "ipv6_spider"
    start_urls = ["http://[::1]"]


if __name__ == "__main__":
    process = CrawlerProcess(settings={"RETRY_ENABLED": False})
    process.crawl(IPv6Spider)
    process.start()
