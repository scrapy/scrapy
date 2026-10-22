import sys

import scrapy
from scrapy.crawler import CrawlerProcess


class BoomSpider(scrapy.Spider):
    name = "boom"

    def __init__(self, *args, **kwargs):
        raise ValueError("boom")


process = CrawlerProcess(settings={})

process.crawl(BoomSpider)
process.start()
print(f"bootstrap_failed: {process.bootstrap_failed}", file=sys.stderr)
