"""
Depth Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

import logging
from typing import Generator, Iterable, Union

from scrapy.http.request import Request, RequestList
from scrapy.http.response import Response, ResponseList
from scrapy.spiders import Spider


logger = logging.getLogger(__name__)


class DepthMiddleware:

    def __init__(self, maxdepth, stats, verbose_stats=False, prio=1):
        self.maxdepth = maxdepth
        self.stats = stats
        self.verbose_stats = verbose_stats
        self.prio = prio

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        maxdepth = settings.getint('DEPTH_LIMIT')
        verbose = settings.getbool('DEPTH_STATS_VERBOSE')
        prio = settings.getint('DEPTH_PRIORITY')
        return cls(maxdepth, crawler.stats, verbose, prio)

    def process_spider_output(
        self, response: Union[Response, ResponseList], result: Iterable, spider: Spider
    ) -> Generator:
        # base case (depth=0)
        if 'depth' not in response.meta:
            response.meta['depth'] = 0
            if self.verbose_stats:
                self.stats.inc_value('request_depth_count/0', spider=spider)

        current_depth = response.meta['depth']

        def _filter(request):
            depth = current_depth + 1
            request.meta['depth'] = depth
            if self.prio:
                request.priority -= depth * self.prio
            if self.maxdepth and depth > self.maxdepth:
                logger.debug(
                    "Ignoring link (depth > %(maxdepth)d): %(requrl)s ",
                    {'maxdepth': self.maxdepth, 'requrl': request.url},
                    extra={'spider': spider}
                )
                return False
            else:
                if self.verbose_stats:
                    self.stats.inc_value(f'request_depth_count/{depth}', spider=spider)
                self.stats.max_value('request_depth_max', depth, spider=spider)
                return True

        for r in result:
            if isinstance(r, RequestList):
                r.requests = list(filter(_filter, r.requests))
                if r.requests:
                    yield r
            elif isinstance(r, Request):
                if _filter(r):
                    yield r
            else:
                yield r
