import warnings
from scrapy.exceptions import ScrapyDeprecationWarning
warnings.warn("Module `scrapy.contrib.downloadermiddleware.robotstxt` is deprecated, "
              "use `scrapy.downloadermiddlewares.robotstxt` instead",
              ScrapyDeprecationWarning, stacklevel=2)

<<<<<<< HEAD
from scrapy.downloadermiddlewares.robotstxt import *
=======
"""

import time

from reppy.parser import Rules
from reppy import Utility

from scrapy import signals, log
from scrapy.exceptions import NotConfigured, IgnoreRequest
from scrapy.http import Request
from scrapy.utils.httpobj import urlparse_cached


class RobotsTxtMiddleware(object):
    DOWNLOAD_PRIORITY = 1000
    default_ttl = 3600
    min_ttl = 60

    def __init__(self, crawler):
        if not crawler.settings.getbool('ROBOTSTXT_OBEY'):
            raise NotConfigured

        self.crawler = crawler
        self._useragent = crawler.settings.get('USER_AGENT')
        self._parsers = {}

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request, spider):
        if request.meta.get('dont_obey_robotstxt'):
            return
        rp = self.robot_parser(request, spider)
        if rp and not rp.allowed(request.url, self._useragent):
            log.msg(format="Forbidden by robots.txt: %(request)s",
                    level=log.DEBUG, request=request)
            raise IgnoreRequest

    def robot_parser(self, request, spider):
        url = urlparse_cached(request)
        netloc = url.netloc
        if netloc not in self._parsers:
            self._parsers[netloc] = None
            robotsurl = "%s://%s/robots.txt" % (url.scheme, url.netloc)
            robotsreq = Request(
                robotsurl,
                priority=self.DOWNLOAD_PRIORITY,
                meta={'dont_obey_robotstxt': True}
            )
            dfd = self.crawler.engine.download(robotsreq, spider)
            dfd.addCallback(self._parse_robots)
        return self._parsers[netloc]

    def _parse_robots(self, response):
        #A lot of work to provide the expire time which we don't actually use
        ttl = max(self.min_ttl, Utility.get_ttl(response.headers, self.default_ttl))
        rp = Rules(response.url, response.status, response.body, time.time() + ttl)
        rp.parse(response.body)
        self._parsers[urlparse_cached(response).netloc] = rp
>>>>>>> 81da1da4d49a5b77e69a11f0b77fe6edcb8e57d5
