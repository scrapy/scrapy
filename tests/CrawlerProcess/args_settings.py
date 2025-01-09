from typing import Any

import scrapy
from scrapy.crawler import Crawler, CrawlerProcess


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    @classmethod
    def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider.settings.set("FOO", kwargs.get("foo"))
        return spider

    def start_requests(self):
        self.logger.info(f"The value of FOO is {self.settings.getint('FOO')}")
        return []


process = CrawlerProcess(settings={})

process.crawl(NoRequestsSpider, foo=42)
process.start()
