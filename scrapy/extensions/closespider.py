"""CloseSpider is an extension that forces spiders to be closed after certain
conditions are met.

See documentation in docs/topics/extensions.rst
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from scrapy import Request, Spider, signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.asyncio import (
    AsyncioLoopingCall,
    CallLaterResult,
    call_later,
    create_looping_call,
)
from scrapy.utils.defer import _schedule_coro

if TYPE_CHECKING:
    from twisted.internet.task import LoopingCall
    from twisted.python.failure import Failure

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Response


logger = logging.getLogger(__name__)


class CloseSpider:
    def __init__(self, crawler: Crawler):
        self.crawler: Crawler = crawler

        # for CLOSESPIDER_TIMEOUT
        self.task: CallLaterResult | None = None

        # for CLOSESPIDER_TIMEOUT_NO_ITEM
        self.task_no_item: AsyncioLoopingCall | LoopingCall | None = None

        self.close_on: dict[str, Any] = {
            "timeout": crawler.settings.getfloat("CLOSESPIDER_TIMEOUT"),
            "itemcount": crawler.settings.getint("CLOSESPIDER_ITEMCOUNT"),
            "pagecount": crawler.settings.getint("CLOSESPIDER_PAGECOUNT"),
            "errorcount": crawler.settings.getint("CLOSESPIDER_ERRORCOUNT"),
            "timeout_no_item": crawler.settings.getint("CLOSESPIDER_TIMEOUT_NO_ITEM"),
            "pagecount_no_item": crawler.settings.getint(
                "CLOSESPIDER_PAGECOUNT_NO_ITEM"
            ),
        }

        if not any(self.close_on.values()):
            raise NotConfigured

        self.counter: defaultdict[str, int] = defaultdict(int)

        if self.close_on.get("errorcount"):
            crawler.signals.connect(self.error_count, signal=signals.spider_error)
        if self.close_on.get("pagecount") or self.close_on.get("pagecount_no_item"):
            crawler.signals.connect(self.page_count, signal=signals.response_received)
        if self.close_on.get("timeout"):
            crawler.signals.connect(self.spider_opened, signal=signals.spider_opened)
        if self.close_on.get("itemcount") or self.close_on.get("pagecount_no_item"):
            crawler.signals.connect(self.item_scraped, signal=signals.item_scraped)
        if self.close_on.get("timeout_no_item"):
            self.timeout_no_item: int = self.close_on["timeout_no_item"]
            self.items_in_period: int = 0
            crawler.signals.connect(
                self.spider_opened_no_item, signal=signals.spider_opened
            )
            crawler.signals.connect(
                self.item_scraped_no_item, signal=signals.item_scraped
            )

        crawler.signals.connect(self.spider_closed, signal=signals.spider_closed)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def error_count(self, failure: Failure, response: Response, spider: Spider) -> None:
        self.counter["errorcount"] += 1
        if self.counter["errorcount"] == self.close_on["errorcount"]:
            self._close_spider("closespider_errorcount")

    def page_count(self, response: Response, request: Request, spider: Spider) -> None:
        self.counter["pagecount"] += 1
        self.counter["pagecount_since_last_item"] += 1
        if self.counter["pagecount"] == self.close_on["pagecount"]:
            self._close_spider("closespider_pagecount")
            return
        if self.close_on["pagecount_no_item"] and (
            self.counter["pagecount_since_last_item"]
            >= self.close_on["pagecount_no_item"]
        ):
            self._close_spider("closespider_pagecount_no_item")

    def spider_opened(self, spider: Spider) -> None:
        assert self.crawler.engine
        self.task = call_later(
            self.close_on["timeout"], self._close_spider, "closespider_timeout"
        )

    def item_scraped(self, item: Any, spider: Spider) -> None:
        self.counter["itemcount"] += 1
        self.counter["pagecount_since_last_item"] = 0
        if self.counter["itemcount"] == self.close_on["itemcount"]:
            self._close_spider("closespider_itemcount")

    def spider_closed(self, spider: Spider) -> None:
        if self.task:
            self.task.cancel()
            self.task = None

        if self.task_no_item:
            if self.task_no_item.running:
                self.task_no_item.stop()
            self.task_no_item = None

    def spider_opened_no_item(self, spider: Spider) -> None:
        self.task_no_item = create_looping_call(self._count_items_produced)
        self.task_no_item.start(self.timeout_no_item, now=False)

        logger.info(
            f"Spider will stop when no items are produced after "
            f"{self.timeout_no_item} seconds."
        )

    def item_scraped_no_item(self, item: Any, spider: Spider) -> None:
        self.items_in_period += 1

    def _count_items_produced(self) -> None:
        if self.items_in_period >= 1:
            self.items_in_period = 0
        else:
            logger.info(
                f"Closing spider since no items were produced in the last "
                f"{self.timeout_no_item} seconds."
            )
            self._close_spider("closespider_timeout_no_item")

    def _close_spider(self, reason: str) -> None:
        assert self.crawler.engine
        _schedule_coro(self.crawler.engine.close_spider_async(reason=reason))
