"""
Url Length Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

import logging

from scrapy.http import Request
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)


class UrlLengthMiddleware:

    def __init__(self, maxlength, stats):
        self.maxlength = maxlength
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        maxlength = settings.getint('URLLENGTH_LIMIT')
        if not maxlength:
            raise NotConfigured
        return cls(maxlength, crawler.stats)

    def process_spider_output(self, response, result, spider):
        def _filter(request):
            if isinstance(request, Request) and len(request.url) > self.maxlength:
                logger.info(
                    "Ignoring link (url length > %(maxlength)d): %(url)s ",
                    {'maxlength': self.maxlength, 'url': request.url},
                    extra={'spider': spider}
                )
                self.stats.inc_value('urllength/request_ignored_count', spider=spider)
                return False
            else:
                return True

        return (r for r in result or () if _filter(r))
