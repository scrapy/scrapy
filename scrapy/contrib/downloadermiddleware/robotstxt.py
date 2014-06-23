"""
This is a middleware to respect robots.txt policies. To activate it you must
enable this middleware and enable the ROBOTSTXT_OBEY setting.

"""

from reppy.cache import RobotsCache

from scrapy import signals, log
from scrapy.exceptions import NotConfigured, IgnoreRequest
from scrapy.http import Request
from scrapy.utils.httpobj import urlparse_cached


class RobotsTxtMiddleware(object):
    DOWNLOAD_PRIORITY = 1000

    def __init__(self, crawler):
        if not crawler.settings.getbool('ROBOTSTXT_OBEY'):
            raise NotConfigured

        self.crawler = crawler
        self._useragent = crawler.settings.get('USER_AGENT')
        self._parsers = {}
        self._spider_netlocs = set()
        
        self.robots = RobotsCache()

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request, spider):
        useragent = self._useragent
        if self.robots and not self.robots.allowed(request.url, useragent):
            log.msg(format="Forbidden by robots.txt: %(request)s",
                    level=log.DEBUG, request=request)
            raise IgnoreRequest
