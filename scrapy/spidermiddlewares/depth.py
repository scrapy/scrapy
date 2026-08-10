"""
Depth Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from scrapy.spidermiddlewares.base import BaseSpiderMiddleware
from scrapy.utils.decorators import _warn_spider_arg

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
    """Track the depth of each request within the site being scraped, setting
    ``request.meta["depth"]`` to 0 when there is no value previously set
    (usually just the first request) and incrementing it by 1 otherwise.

    It can be used to limit the maximum depth to scrape, control request
    priority based on their depth, and things like that, through the
    :setting:`DEPTH_LIMIT`, :setting:`DEPTH_STATS_VERBOSE` and
    :setting:`DEPTH_PRIORITY` settings.

    .. reqmeta:: depth_reset

    depth_reset
    -----------

    .. versionadded:: VERSION

    :attr:`~scrapy.Request.meta` key that, set to ``True``, gives a request
    depth 0 instead of the depth of its source response plus 1, e.g. to keep
    :setting:`DEPTH_LIMIT` from applying across a domain change.
    """

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
        self._ignored_logged = False

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

    @_warn_spider_arg
    def process_spider_output(
        self,
        response: Response | None,
        result: Iterable[Any],
        spider: Spider | None = None,
    ) -> Iterable[Any]:
        if response is not None:
            self._init_depth(response)
        yield from super().process_spider_output(response, result)

    @_warn_spider_arg
    async def process_spider_output_async(
        self,
        response: Response | None,
        result: AsyncIterator[Any],
        spider: Spider | None = None,
    ) -> AsyncIterator[Any]:
        if response is not None:
            self._init_depth(response)
        async for o in super().process_spider_output_async(response, result):
            yield o

    def _init_depth(self, response: Response) -> None:
        # base case (depth=0)
        if "depth" not in response.meta:
            response.meta["depth"] = 0
            if self.verbose_stats:
                self.stats.inc_value("request_depth_count/0")

    def get_processed_request(
        self, request: Request, response: Response | None
    ) -> Request | None:
        # Consumed here so that it cannot reach response.meta and, from there,
        # spread to further requests through a meta copy.
        depth_reset = request.meta.pop("depth_reset", False)
        if response is None:
            # start requests
            return request
        depth = 0 if depth_reset else response.meta["depth"] + 1
        request.meta["depth"] = depth
        if self.prio:
            request.priority -= depth * self.prio
        if self.maxdepth and depth > self.maxdepth:
            if not self._ignored_logged:
                logger.debug(
                    f"Ignoring link (depth > {self.maxdepth}): {request.url}"
                    " - no more ignored links will be shown",
                    extra={"spider": self.crawler.spider},
                )
                self._ignored_logged = True
            self.stats.inc_value("depth/request_ignored_count")
            return None
        if self.verbose_stats:
            self.stats.inc_value(f"request_depth_count/{depth}")
        self.stats.max_value("request_depth_max", depth)
        return request
