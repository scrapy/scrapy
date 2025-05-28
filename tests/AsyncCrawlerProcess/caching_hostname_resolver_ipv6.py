import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class CachingHostnameResolverSpider(scrapy.Spider):
    """
    Finishes without a twisted.internet.error.DNSLookupError exception
    """

    name = "caching_hostname_resolver_spider"
    start_urls = ["http://[::1]"]


if __name__ == "__main__":
    process = AsyncCrawlerProcess(
        settings={
            "RETRY_ENABLED": False,
            "DNS_RESOLVER": "scrapy.resolver.CachingHostnameResolver",
        }
    )
    process.crawl(CachingHostnameResolverSpider)
    process.start()
