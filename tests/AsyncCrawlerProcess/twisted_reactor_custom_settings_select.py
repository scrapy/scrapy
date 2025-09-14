from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import scrapy
from scrapy.crawler import AsyncCrawlerProcess

if TYPE_CHECKING:
    from asyncio import Task


class AsyncioReactorSpider(scrapy.Spider):
    name = "asyncio_reactor"
    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.selectreactor.SelectReactor",
    }


def log_task_exception(task: Task) -> None:
    try:
        task.result()
    except Exception:
        logging.exception("Crawl task failed")  # noqa: LOG015


process = AsyncCrawlerProcess()
task = process.crawl(AsyncioReactorSpider)
task.add_done_callback(log_task_exception)
process.start()
