"""
Depth Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from scrapy.http import Request, Response

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Iterable

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


logger = logging.getLogger(__name__)


class DepthMiddleware:
    def __init__(
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
        return cls(maxdepth, crawler.stats, verbose, prio)

    def process_spider_output(
        self, response: Response, result: Iterable[Any], spider: Spider
    ) -> Iterable[Any]:
        self._init_depth(response, spider)
        return (r for r in result if self._filter(r, response, spider))

    async def process_spider_output_async(
        self, response: Response, result: AsyncIterable[Any], spider: Spider
    ) -> AsyncIterable[Any]:
        self._init_depth(response, spider)
        async for r in result:
            if self._filter(r, response, spider):
                yield r

    def _init_depth(self, response: Response, spider: Spider) -> None:
        # base case (depth=0)
        if "depth" not in response.meta:
            response.meta["depth"] = 0
            if self.verbose_stats:
                self.stats.inc_value("request_depth_count/0", spider=spider)

    def _filter(self, request: Any, response: Response, spider: Spider) -> bool:
        if not isinstance(request, Request):
            return True
        depth = response.meta["depth"] + 1
        request.meta["depth"] = depth
        if self.prio:
            request.priority -= depth * self.prio
        if self.maxdepth and depth > self.maxdepth:
            logger.debug(
                "Ignoring link (depth > %(maxdepth)d): %(requrl)s ",
                {"maxdepth": self.maxdepth, "requrl": request.url},
                extra={"spider": spider},
            )
            return False
        if self.verbose_stats:
            self.stats.inc_value(f"request_depth_count/{depth}", spider=spider)
        self.stats.max_value("request_depth_max", depth, spider=spider)
        return True
