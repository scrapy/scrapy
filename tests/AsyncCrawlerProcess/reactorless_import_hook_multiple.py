import sys

import scrapy
from scrapy.crawler import AsyncCrawlerProcess
from scrapy.utils.reactorless import ReactorImportHook


def hook_count() -> int:
    return sum(1 for finder in sys.meta_path if isinstance(finder, ReactorImportHook))


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        self.logger.info(f"Hooks during run: {hook_count()}")
        return
        yield


for _ in range(2):
    process = AsyncCrawlerProcess(settings={"TWISTED_REACTOR_ENABLED": False})
    process.crawl(NoRequestsSpider)
    process.start()

print(f"Hooks after runs: {hook_count()}", file=sys.stderr)
