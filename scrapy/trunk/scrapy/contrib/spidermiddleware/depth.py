"""
DepthMiddleware is a scrape middleware used for tracking the depth of each
Request inside the site being scraped. It can be used to limit the maximum
depth to scrape or things like that
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
            stats.setpath('_envinfo/request_depth_limit', self.maxdepth)

    def process_spider_output(self, response, result, spider):
        def _filter(request):
            if isinstance(request, Request):
                request.depth = response.request.depth + 1
                if self.maxdepth and request.depth > self.maxdepth:
                    log.msg("Ignoring link (depth > %d): %s " % (self.maxdepth, request.url), level=log.DEBUG, domain=spider.domain_name)
                    return False
                elif self.stats:
                    stats.incpath('%s/request_depth_count/%s' % (spider.domain_name, request.depth))
                    if request.depth > stats.getpath('%s/request_depth_max' % spider.domain_name, 0):
                        stats.setpath('%s/request_depth_max' % spider.domain_name, request.depth)
            return True

        if self.stats and response.request.depth == 0: # otherwise we loose stats for depth=0 
            stats.incpath('%s/request_depth_count/0' % spider.domain_name)

        return (r for r in result or () if _filter(r))
