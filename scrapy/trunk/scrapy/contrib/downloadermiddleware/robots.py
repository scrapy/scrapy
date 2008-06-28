"""
jhis is an expertimental middleware to respect robots.txt policies. The biggest
problem it has is that it uses urllib directly (in RobotFileParser.read()
method) and that conflicts with twisted networking, so it should be ported to
use twisted networking API, but that is not as trivial as it may seem.

This code is left here for future reference, when we resume the work on this
subject.

"""

import re
import urlparse
import robotparser

from pydispatch import dispatcher

from scrapy.core import log, signals
from scrapy.core.exceptions import IgnoreRequest
from scrapy.conf import settings

BASEURL_RE = re.compile("http://.*?/")

class RobotsMiddleware(object):

    def __init__(self):
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
        urldomain = urlparse.urlparse(url).hostname
        if urldomain in self._parsers:
            rp = self._parsers[urldomain]
        else:
            rp = robotparser.RobotFileParser()
            m = BASEURL_RE.search(url)
            if m:
                rp.set_url("%srobots.txt" % m.group())
                rp.read()
            self._parsers[urldomain] = rp
            self._spiderdomains[spiderdomain].add(urldomain)
        return rp

    def domain_open(self, domain):
        self._spiderdomains[domain] = set()

    def domain_closed(self, domain):
        for urldomain in self._spiderdomains[domain]:
            del self._parsers[urldomain]
        del self._spiderdomains[domain]
