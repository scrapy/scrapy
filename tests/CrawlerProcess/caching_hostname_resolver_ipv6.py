import scrapy
from scrapy.crawler import CrawlerProcess


class CachingHostnameResolverSpider(scrapy.Spider):
    """
    Finishes without a scrapy.exceptions.CannotResolveHostError exception
    """

    name = "caching_hostname_resolver_spider"
    start_urls = ["http://[::1]"]


if __name__ == "__main__":
    process = CrawlerProcess(
        settings={
            "RETRY_ENABLED": False,
            "DNS_RESOLVER": "scrapy.resolver.CachingHostnameResolver",
        }
    )
    process.crawl(CachingHostnameResolverSpider)
    process.start()
