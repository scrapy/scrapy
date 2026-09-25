import sys

import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class BoomSpider(scrapy.Spider):
    name = "boom"

    def __init__(self, *args, **kwargs):
        raise ValueError("boom")


process = AsyncCrawlerProcess(settings={})

process.crawl(BoomSpider)
process.start()
print(f"bootstrap_failed: {process.bootstrap_failed}", file=sys.stderr)
