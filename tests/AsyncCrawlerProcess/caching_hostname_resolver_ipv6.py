import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class CachingHostnameResolverSpider(scrapy.Spider):
    """
    Finishes without a scrapy.exceptions.CannotResolveHostError exception
    """

    name = "caching_hostname_resolver_spider"

    async def start(self):
        # w3lib older than 2.4.1 strips the brackets, making the URL invalid.
        yield scrapy.Request("http://[::1]", meta={"verbatim_url": True})


if __name__ == "__main__":
    process = AsyncCrawlerProcess(
        settings={
            "RETRY_ENABLED": False,
            "TWISTED_DNS_RESOLVER": "scrapy.resolver.CachingHostnameResolver",
        }
    )
    process.crawl(CachingHostnameResolverSpider)
    process.start()
