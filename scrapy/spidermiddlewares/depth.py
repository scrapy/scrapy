"""
Depth Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

import logging

from scrapy.http import Request

logger = logging.getLogger(__name__)


class DepthMiddleware(object):
    """DepthMiddleware is used for tracking the depth of each Request inside the
   site being scraped. It works by setting `request.meta['depth'] = 0` whenever
   there is no value previously set (usually just the first Request) and
   incrementing it by 1 otherwise.

   It can be used to limit the maximum depth to scrape, control Request
   priority based on their depth, and things like that.

   The :class:`DepthMiddleware` can be configured through the following
   settings (see the settings documentation for more info):

      * :setting:`DEPTH_LIMIT` - The maximum depth that will be allowed to
        crawl for any site. If zero, no limit will be imposed.
      * :setting:`DEPTH_STATS_VERBOSE` - Whether to collect the number of
        requests for each depth.
      * :setting:`DEPTH_PRIORITY` - Whether to prioritize the requests based on
        their depth.
    """

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

    def process_spider_output(self, response, result, spider):
        def _filter(request):
            if isinstance(request, Request):
                depth = response.meta['depth'] + 1
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
                        self.stats.inc_value('request_depth_count/%s' % depth,
                                             spider=spider)
                    self.stats.max_value('request_depth_max', depth,
                                         spider=spider)
            return True

        # base case (depth=0)
        if 'depth' not in response.meta:
            response.meta['depth'] = 0
            if self.verbose_stats:
                self.stats.inc_value('request_depth_count/0', spider=spider)

        return (r for r in result or () if _filter(r))
