import asyncio
import os
import sys
import time

import scrapy
from scrapy.crawler import AsyncCrawlerProcess


class SleepingSpider(scrapy.Spider):
    name = "sleeping"

    start_urls = ["data:,;"]

    async def parse(self, response):
        os.write(2, f"SIGDIAG parse-start mono={time.monotonic():.3f}\n".encode())
        await asyncio.sleep(int(sys.argv[1]))
        os.write(2, f"SIGDIAG parse-end mono={time.monotonic():.3f}\n".encode())


process = AsyncCrawlerProcess(settings={})

process.crawl(SleepingSpider)
process.start(stop_after_crawl="--no-stop" not in sys.argv)
