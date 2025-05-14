"""
Url Length Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scrapy.exceptions import NotConfigured
from scrapy.spidermiddlewares.base import BaseSpiderMiddleware

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response


logger = logging.getLogger(__name__)


class UrlLengthMiddleware(BaseSpiderMiddleware):
    crawler: Crawler

    def __init__(self, maxlength: int):  # pylint: disable=super-init-not-called
        self.maxlength: int = maxlength

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        maxlength = crawler.settings.getint("URLLENGTH_LIMIT")
        if not maxlength:
            raise NotConfigured
        o = cls(maxlength)
        o.crawler = crawler
        return o

    def get_processed_request(
        self, request: Request, response: Response | None
    ) -> Request | None:
        if len(request.url) <= self.maxlength:
            return request
        logger.info(
            "Ignoring link (url length > %(maxlength)d): %(url)s ",
            {"maxlength": self.maxlength, "url": request.url},
            extra={"spider": self.crawler.spider},
        )
        assert self.crawler.stats
        self.crawler.stats.inc_value(
            "urllength/request_ignored_count", spider=self.crawler.spider
        )
        return None
