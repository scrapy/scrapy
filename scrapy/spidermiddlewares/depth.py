"""
Depth Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from scrapy.spidermiddlewares.base import BaseSpiderMiddleware

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response
    from scrapy.statscollectors import StatsCollector


logger = logging.getLogger(__name__)


class DepthMiddleware(BaseSpiderMiddleware):
    crawler: Crawler

    def __init__(  # pylint: disable=super-init-not-called
        self,
        maxdepth: int,
        stats: StatsCollector,
        verbose_stats: bool = False,
        prio: int = 1,
    ):
        self.maxdepth = maxdepth
        self.stats = stats
        self.verbose_stats = verbose_stats
        self.prio = prio

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        settings = crawler.settings
        maxdepth = settings.getint("DEPTH_LIMIT")
        verbose = settings.getbool("DEPTH_STATS_VERBOSE")
        prio = settings.getint("DEPTH_PRIORITY")
        assert crawler.stats
        o = cls(maxdepth, crawler.stats, verbose, prio)
        o.crawler = crawler
        return o

    def process_spider_output(
        self, response: Response, result: Iterable[Any], spider: Spider
    ) -> Iterable[Any]:
        self._init_depth(response, spider)
        yield from super().process_spider_output(response, result, spider)

    async def process_spider_output_async(
        self, response: Response, result: AsyncIterator[Any], spider: Spider
    ) -> AsyncIterator[Any]:
        self._init_depth(response, spider)
        async for o in super().process_spider_output_async(response, result, spider):
            yield o

    def _init_depth(self, response: Response, spider: Spider) -> None:
        # base case (depth=0)
        if "depth" not in response.meta:
            response.meta["depth"] = 0
            if self.verbose_stats:
                self.stats.inc_value("request_depth_count/0", spider=spider)

    def get_processed_request(
        self, request: Request, response: Response | None
    ) -> Request | None:
        if response is None:
            # start requests
            return request
        depth = response.meta["depth"] + 1
        request.meta["depth"] = depth
        if self.prio:
            request.priority -= depth * self.prio
        if self.maxdepth and depth > self.maxdepth:
            logger.debug(
                "Ignoring link (depth > %(maxdepth)d): %(requrl)s ",
                {"maxdepth": self.maxdepth, "requrl": request.url},
                extra={"spider": self.crawler.spider},
            )
            return None
        if self.verbose_stats:
            self.stats.inc_value(
                f"request_depth_count/{depth}", spider=self.crawler.spider
            )
        self.stats.max_value("request_depth_max", depth, spider=self.crawler.spider)
        return request
