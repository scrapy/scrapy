"""
This is a middleware to respect robots.txt policies. To active it you must
enable this middleware and enable the ROBOTSTXT_OBEY setting.

"""

import urlparse
import robotparser

from scrapy.xlib.pydispatch import dispatcher

from scrapy.core import signals
from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import NotConfigured
from scrapy.spider import spiders
from scrapy.http import Request
from scrapy.core.exceptions import IgnoreRequest
from scrapy.conf import settings

class RobotsTxtMiddleware(object):
    DOWNLOAD_PRIORITY = 1000

    def __init__(self):
        if not settings.getbool('ROBOTSTXT_OBEY'):
            raise NotConfigured

        self._parsers = {}
        self._spiderdomains = {}
        self._pending = {}
        dispatcher.connect(self.domain_open, signals.domain_open)
        dispatcher.connect(self.domain_closed, signals.domain_closed)

    def process_request(self, request, spider):
        agent = getattr(spider, 'user_agent', None) or settings['USER_AGENT']
        rp = self.robot_parser(request.url, spider.domain_name)
        if rp and not rp.can_fetch(agent, request.url):
            raise IgnoreRequest("URL forbidden by robots.txt: %s" % request.url)

    def robot_parser(self, url, spiderdomain):
        parsedurl = urlparse.urlparse(url)
        urldomain = parsedurl.hostname
        if urldomain in self._parsers:
            return self._parsers[urldomain]
        else:
            self._parsers[urldomain] = None
            robotsurl = "%s://%s/robots.txt" % parsedurl[0:2]
            robotsreq = Request(robotsurl, priority=self.DOWNLOAD_PRIORITY)
            dfd = scrapyengine.download(robotsreq, spiders.fromdomain(spiderdomain))
            dfd.addCallbacks(callback=self._parse_robots, callbackArgs=[urldomain])
            self._spiderdomains[spiderdomain].add(urldomain)

    def _parse_robots(self, response, urldomain):
        rp = robotparser.RobotFileParser()
        rp.parse(response.to_string().splitlines())
        self._parsers[urldomain] = rp

    def domain_open(self, domain):
        self._spiderdomains[domain] = set()

    def domain_closed(self, domain):
        for urldomain in self._spiderdomains[domain]:
            del self._parsers[urldomain]
        del self._spiderdomains[domain]
