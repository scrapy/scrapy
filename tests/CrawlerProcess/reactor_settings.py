import sys

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.resolver import dnscache


class Spider1(scrapy.Spider):
    name = "spider1"
    custom_settings = {
        "DNSCACHE_ENABLED": False,
        "DNS_TIMEOUT": 11,
        "REACTOR_THREADPOOL_MAXSIZE": 42,
    }

    async def start(self):
        from twisted.internet import reactor

        self.logger.info(f"DNS timeout: {reactor.resolver.timeout}")
        self.logger.info(f"DNS cache limit: {dnscache.limit}")
        self.logger.info(f"Thread pool size: {reactor.getThreadPool().max}")
        return
        yield


class Spider2(Spider1):
    name = "spider2"
    custom_settings = {**Spider1.custom_settings, "DNS_TIMEOUT": 22}


process = CrawlerProcess()
process.crawl(Spider1)
if len(sys.argv) > 1 and sys.argv[1] == "conflict":
    process.crawl(Spider2)
process.start()
