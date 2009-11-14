"""
Depth Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

from scrapy import log
from scrapy.http import Request
from scrapy.stats import stats
from scrapy.conf import settings

class DepthMiddleware(object):

    def __init__(self):
        self.maxdepth = settings.getint('DEPTH_LIMIT')
        self.stats = settings.getbool('DEPTH_STATS')
        if self.stats and self.maxdepth:
            stats.set_value('envinfo/request_depth_limit', self.maxdepth)

    def process_spider_output(self, response, result, spider):
        def _filter(request):
            if isinstance(request, Request):
                depth = response.request.meta['depth'] + 1
                request.meta['depth'] = depth
                if self.maxdepth and depth > self.maxdepth:
                    log.msg("Ignoring link (depth > %d): %s " % (self.maxdepth, request.url), \
                        level=log.DEBUG, spider=spider)
                    return False
                elif self.stats:
                    stats.inc_value('request_depth_count/%s' % depth, spider=spider)
                    if depth > stats.get_value('request_depth_max', 0, spider=spider):
                        stats.set_value('request_depth_max', depth, spider=spider)
            return True

        # base case (depth=0)
        if self.stats and 'depth' not in response.request.meta: 
            response.request.meta['depth'] = 0
            stats.inc_value('request_depth_count/0', spider=spider)

        return (r for r in result or () if _filter(r))
