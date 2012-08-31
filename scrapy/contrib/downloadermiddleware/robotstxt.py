"""
This is a middleware to respect robots.txt policies. To activate it you must
enable this middleware and enable the ROBOTSTXT_OBEY setting.

"""

import robotparser

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
        self._parsers = {}
        self._spider_netlocs = {}
        self._useragents = {}
        crawler.signals.connect(self.spider_opened, signals.spider_opened)
        crawler.signals.connect(self.spider_closed, signals.spider_closed)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request, spider):
        useragent = self._useragents[spider]
        rp = self.robot_parser(request, spider)
        if rp and not rp.can_fetch(useragent, request.url):
            log.msg(format="Forbidden by robots.txt: %(request)s",
                    level=log.DEBUG, request=request)
            raise IgnoreRequest

    def robot_parser(self, request, spider):
        url = urlparse_cached(request)
        netloc = url.netloc
        if netloc not in self._parsers:
            self._parsers[netloc] = None
            robotsurl = "%s://%s/robots.txt" % (url.scheme, url.netloc)
            robotsreq = Request(robotsurl, priority=self.DOWNLOAD_PRIORITY)
            dfd = self.crawler.engine.download(robotsreq, spider)
            dfd.addCallback(self._parse_robots)
            self._spider_netlocs[spider].add(netloc)
        return self._parsers[netloc]

    def _parse_robots(self, response):
        rp = robotparser.RobotFileParser(response.url)
        rp.parse(response.body.splitlines())
        self._parsers[urlparse_cached(response).netloc] = rp

    def spider_opened(self, spider):
        self._spider_netlocs[spider] = set()
        self._useragents[spider] = spider.settings['USER_AGENT']

    def spider_closed(self, spider):
        for netloc in self._spider_netlocs[spider]:
            del self._parsers[netloc]
        del self._spider_netlocs[spider]
        del self._useragents[spider]
