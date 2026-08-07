import sys

import scrapy
from scrapy.crawler import AsyncCrawlerProcess
from scrapy.settings import Settings


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


settings = Settings()
# The deprecated DNS_RESOLVER setting, set above its default priority so that
# AsyncCrawlerProcess._setup_reactor() emits the deprecation warning.
settings.set("DNS_RESOLVER", "scrapy.resolver.CachingThreadedResolver", priority=10)
if len(sys.argv) > 1 and sys.argv[1] == "twisted-wins":
    # TWISTED_DNS_RESOLVER at a higher priority takes precedence over the
    # deprecated DNS_RESOLVER setting.
    settings.set(
        "TWISTED_DNS_RESOLVER",
        "scrapy.resolver.CachingThreadedResolver",
        priority=20,
    )

process = AsyncCrawlerProcess(settings)
process.crawl(NoRequestsSpider)
process.start()
