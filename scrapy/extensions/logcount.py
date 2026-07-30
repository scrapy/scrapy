from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scrapy import Spider, signals
from scrapy.utils.log import LogCounterHandler

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)


class LogCount:
    """Install a log handler that counts log messages by level.

    The handler installed is :class:`scrapy.utils.log.LogCounterHandler`.
    The counts are stored in stats as ``log_count/<level>``.

    .. versionadded:: 2.14
    """

    def __init__(self, crawler: Crawler):
        self.crawler: Crawler = crawler
        self.handler: LogCounterHandler | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        o = cls(crawler)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_opened(self, spider: Spider) -> None:
        self.handler = LogCounterHandler(
            self.crawler, level=self.crawler.settings.get("LOG_LEVEL")
        )
        logging.root.addHandler(self.handler)

    def spider_closed(self, spider: Spider, reason: str) -> None:
        if self.handler:
            logging.root.removeHandler(self.handler)
            self.handler = None
