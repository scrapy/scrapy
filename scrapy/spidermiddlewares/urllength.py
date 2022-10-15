"""
Url Length Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

import logging

from scrapy.http import Request
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)


class UrlLengthMiddleware:

    def __init__(self, maxlength):
        self.maxlength = maxlength

    @classmethod
    def from_settings(cls, settings):
        maxlength = settings.getint('URLLENGTH_LIMIT')
        if not maxlength:
            raise NotConfigured
        return cls(maxlength)

    def process_spider_output(self, response, result, spider):
        return (r for r in result or () if self._filter(r, spider))

    async def process_spider_output_async(self, response, result, spider):
        async for r in result or ():
            if self._filter(r, spider):
                yield r

    def _filter(self, request, spider):
        if isinstance(request, Request) and len(request.url) > self.maxlength:
            logger.info(
                "Ignoring link (url length > %(maxlength)d): %(url)s ",
                {'maxlength': self.maxlength, 'url': request.url},
                extra={'spider': spider}
            )
            spider.crawler.stats.inc_value('urllength/request_ignored_count', spider=spider)
            return False
        return True
