"""
Url Length Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

import logging

from scrapy.exceptions import NotConfigured
from scrapy.http import Request

logger = logging.getLogger(__name__)


class UrlLengthMiddleware(object):

    def __init__(self, maxlength):
        self.maxlength = maxlength

    @classmethod
    def from_settings(cls, settings):
        maxlength = settings.getint('URLLENGTH_LIMIT')
        if not maxlength:
            raise NotConfigured
        return cls(maxlength)

    def process_spider_output(self, response, result, spider):
        def _filter(request):
            if isinstance(request, Request) and len(request.url) > self.maxlength:
                logger.debug("Ignoring link (url length > %(maxlength)d): %(url)s ",
                             {'maxlength': self.maxlength, 'url': request.url},
                             extra={'spider': spider})
                return False
            else:
                return True

        return (r for r in result or () if _filter(r))
