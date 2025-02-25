"""
Url Length Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.spidermiddlewares.base import BaseSpiderMiddleware

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


class UrlLengthMiddleware(BaseSpiderMiddleware):
    def __init__(self, maxlength: int):
        self.maxlength: int = maxlength

    @classmethod
    def from_settings(cls, settings: BaseSettings) -> Self:
        warnings.warn(
            f"{cls.__name__}.from_settings() is deprecated, use from_crawler() instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return cls._from_settings(settings)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls._from_settings(crawler.settings)

    @classmethod
    def _from_settings(cls, settings: BaseSettings) -> Self:
        maxlength = settings.getint("URLLENGTH_LIMIT")
        if not maxlength:
            raise NotConfigured
        return cls(maxlength)

    def _process_request(
        self, request: Request, response: Response, spider: Spider
    ) -> Request | None:
        if len(request.url) <= self.maxlength:
            return request
        logger.info(
            "Ignoring link (url length > %(maxlength)d): %(url)s ",
            {"maxlength": self.maxlength, "url": request.url},
            extra={"spider": spider},
        )
        assert spider.crawler.stats
        spider.crawler.stats.inc_value("urllength/request_ignored_count", spider=spider)
        return None
