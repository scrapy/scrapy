"""
Url Length Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, Any

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.http import Request, Response

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Iterable

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


class UrlLengthMiddleware:
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

    def process_spider_output(
        self, response: Response, result: Iterable[Any], spider: Spider
    ) -> Iterable[Any]:
        return (r for r in result if self._filter(r, spider))

    async def process_spider_output_async(
        self, response: Response, result: AsyncIterable[Any], spider: Spider
    ) -> AsyncIterable[Any]:
        async for r in result:
            if self._filter(r, spider):
                yield r

    def _filter(self, request: Any, spider: Spider) -> bool:
        if isinstance(request, Request) and len(request.url) > self.maxlength:
            logger.info(
                "Ignoring link (url length > %(maxlength)d): %(url)s ",
                {"maxlength": self.maxlength, "url": request.url},
                extra={"spider": spider},
            )
            assert spider.crawler.stats
            spider.crawler.stats.inc_value(
                "urllength/request_ignored_count", spider=spider
            )
            return False
        return True
