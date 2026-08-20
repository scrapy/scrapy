import os
import sys
import time

from twisted.internet.defer import Deferred

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.defer import maybe_deferred_to_future


class SleepingSpider(scrapy.Spider):
    name = "sleeping"

    start_urls = ["data:,;"]

    async def parse(self, response):
        from twisted.internet import reactor

        os.write(2, f"SIGDIAG parse-start mono={time.monotonic():.3f}\n".encode())
        d: Deferred[None] = Deferred()
        reactor.callLater(int(sys.argv[1]), d.callback, None)
        await maybe_deferred_to_future(d)
        os.write(2, f"SIGDIAG parse-end mono={time.monotonic():.3f}\n".encode())


process = CrawlerProcess(settings={})

process.crawl(SleepingSpider)
process.start(stop_after_crawl="--no-stop" not in sys.argv)
