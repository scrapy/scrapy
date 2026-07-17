import sys

import scrapy
from scrapy.crawler import AsyncCrawlerProcess
from scrapy.utils.reactorless import ReactorImportHook


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = AsyncCrawlerProcess(settings={"TWISTED_REACTOR_ENABLED": False})

process.crawl(NoRequestsSpider)
process.start()

hook_count = sum(1 for finder in sys.meta_path if isinstance(finder, ReactorImportHook))
print(f"Hooks in sys.meta_path after start(): {hook_count}", file=sys.stderr)

import twisted.internet.reactor  # noqa: E402,F401,TID253

print("Reactor imported after start()", file=sys.stderr)
