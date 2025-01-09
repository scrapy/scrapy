"""Set User-Agent header per spider or use a default value from settings"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy import Request, Spider, signals

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Response


class UserAgentMiddleware:
    """This middleware allows spiders to override the user_agent"""

    def __init__(self, user_agent: str = "Scrapy"):
        self.user_agent = user_agent

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        o = cls(crawler.settings["USER_AGENT"])
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider: Spider) -> None:
        self.user_agent = getattr(spider, "user_agent", self.user_agent)

    def process_request(
        self, request: Request, spider: Spider
    ) -> Request | Response | None:
        if self.user_agent:
            request.headers.setdefault(b"User-Agent", self.user_agent)
        return None
