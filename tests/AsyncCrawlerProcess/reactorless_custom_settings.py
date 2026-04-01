from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import scrapy
from scrapy.crawler import AsyncCrawlerProcess
from scrapy.utils.reactorless import is_reactorless

if TYPE_CHECKING:
    from asyncio import Task


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"
    custom_settings = {
        "TWISTED_ENABLED": False,
    }

    async def start(self):
        self.logger.info(f"is_reactorless(): {is_reactorless()}")
        return
        yield


def log_task_exception(task: Task) -> None:
    try:
        task.result()
    except Exception:
        logging.exception("Crawl task failed")  # noqa: LOG015


process = AsyncCrawlerProcess()
task = process.crawl(NoRequestsSpider)
task.add_done_callback(log_task_exception)
process.start()
