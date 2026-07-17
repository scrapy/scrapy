import logging
import sys

import scrapy
from scrapy.crawler import AsyncCrawlerProcess
from scrapy.utils.reactorless import ReactorImportHook

logger = logging.getLogger(__name__)


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


process = AsyncCrawlerProcess(settings={"TWISTED_REACTOR_ENABLED": False})

process.crawl(NoRequestsSpider)
process.start()

hook_count = sum(1 for finder in sys.meta_path if isinstance(finder, ReactorImportHook))
logger.info(f"Hooks in sys.meta_path after start(): {hook_count}")

import twisted.internet.reactor  # noqa: E402,F401,TID253

logger.info("Reactor imported after start()")
