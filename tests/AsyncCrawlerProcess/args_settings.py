from typing import Any

import scrapy
from scrapy.crawler import AsyncCrawlerProcess, Crawler


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    @classmethod
    def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider.settings.set("FOO", kwargs.get("foo"))
        return spider

    async def start(self):
        self.logger.info(f"The value of FOO is {self.settings.getint('FOO')}")
        return
        yield


process = AsyncCrawlerProcess(settings={})

process.crawl(NoRequestsSpider, foo=42)
process.start()
