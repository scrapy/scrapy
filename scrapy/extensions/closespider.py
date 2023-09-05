"""CloseSpider is an extension that forces spiders to be closed after certain
conditions are met.

See documentation in docs/topics/extensions.rst
"""

import logging
from collections import defaultdict

from scrapy import signals
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)


class CloseSpider:
    def __init__(self, crawler):
        self.crawler = crawler

        self.close_on = {
            "timeout": crawler.settings.getfloat("CLOSESPIDER_TIMEOUT"),
            "itemcount": crawler.settings.getint("CLOSESPIDER_ITEMCOUNT"),
            "pagecount": crawler.settings.getint("CLOSESPIDER_PAGECOUNT"),
            "errorcount": crawler.settings.getint("CLOSESPIDER_ERRORCOUNT"),
            "timeout_no_item": crawler.settings.getint("CLOSESPIDER_TIMEOUT_NO_ITEM"),
        }

        if not any(self.close_on.values()):
            raise NotConfigured

        self.counter = defaultdict(int)

        if self.close_on.get("errorcount"):
            crawler.signals.connect(self.error_count, signal=signals.spider_error)
        if self.close_on.get("pagecount"):
            crawler.signals.connect(self.page_count, signal=signals.response_received)
        if self.close_on.get("timeout"):
            crawler.signals.connect(self.spider_opened, signal=signals.spider_opened)
        if self.close_on.get("itemcount"):
            crawler.signals.connect(self.item_scraped, signal=signals.item_scraped)
        if self.close_on.get("timeout_no_item"):
            self.timeout_no_item = self.close_on["timeout_no_item"]
            self.items_in_period = 0
            crawler.signals.connect(
                self.spider_opened_no_item, signal=signals.spider_opened
            )
            crawler.signals.connect(
                self.item_scraped_no_item, signal=signals.item_scraped
            )
        crawler.signals.connect(self.spider_closed, signal=signals.spider_closed)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def error_count(self, failure, response, spider):
        self.counter["errorcount"] += 1
        if self.counter["errorcount"] == self.close_on["errorcount"]:
            self.crawler.engine.close_spider(spider, "closespider_errorcount")

    def page_count(self, response, request, spider):
        self.counter["pagecount"] += 1
        if self.counter["pagecount"] == self.close_on["pagecount"]:
            self.crawler.engine.close_spider(spider, "closespider_pagecount")

    def spider_opened(self, spider):
        from twisted.internet import reactor

        self.task = reactor.callLater(
            self.close_on["timeout"],
            self.crawler.engine.close_spider,
            spider,
            reason="closespider_timeout",
        )

    def item_scraped(self, item, spider):
        self.counter["itemcount"] += 1
        if self.counter["itemcount"] == self.close_on["itemcount"]:
            self.crawler.engine.close_spider(spider, "closespider_itemcount")

    def spider_closed(self, spider):
        task = getattr(self, "task", False)
        if task and task.active():
            task.cancel()

        task_no_item = getattr(self, "task_no_item", False)
        if task_no_item and task_no_item.running:
            task_no_item.stop()

    def spider_opened_no_item(self, spider):
        from twisted.internet import task

        self.task_no_item = task.LoopingCall(self._count_items_produced, spider)
        self.task_no_item.start(self.timeout_no_item, now=False)

        logger.info(
            f"Spider will stop when no items are produced after "
            f"{self.timeout_no_item} seconds."
        )

    def item_scraped_no_item(self, item, spider):
        self.items_in_period += 1

    def _count_items_produced(self, spider):
        if self.items_in_period >= 1:
            self.items_in_period = 0
        else:
            logger.info(
                f"Closing spider since no items were produced in the last "
                f"{self.timeout_no_item} seconds."
            )
            self.crawler.engine.close_spider(spider, "closespider_timeout_no_item")
