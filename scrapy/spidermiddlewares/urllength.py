"""
Url Length Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

import logging
from typing import Generator, Iterable, Union

from scrapy.exceptions import NotConfigured
from scrapy.http.request import Request, RequestList
from scrapy.http.response import Response, ResponseList
from scrapy.spiders import Spider

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

    def process_spider_output(
        self, response: Union[Response, ResponseList], result: Iterable, spider: Spider
    ) -> Generator:
        def _filter(request):
            if len(request.url) > self.maxlength:
                logger.info(
                    "Ignoring link (url length > %(maxlength)d): %(url)s ",
                    {'maxlength': self.maxlength, 'url': request.url},
                    extra={'spider': spider}
                )
                spider.crawler.stats.inc_value('urllength/request_ignored_count', spider=spider)
                return False
            else:
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
