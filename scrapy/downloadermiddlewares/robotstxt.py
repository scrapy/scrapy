"""
This is a middleware to respect robots.txt policies. To activate it you must
enable this middleware and enable the ROBOTSTXT_OBEY setting.

"""

import logging

from six.moves.urllib import robotparser

from twisted.internet.defer import Deferred, maybeDeferred
from scrapy.exceptions import NotConfigured, IgnoreRequest
from scrapy.http import Request
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.python import to_native_str

logger = logging.getLogger(__name__)


class RobotsTxtMiddleware(object):
    DOWNLOAD_PRIORITY = 1000

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
        d = maybeDeferred(self.robot_parser, request, spider)
        d.addCallback(self.process_request_2, request, spider)
        return d

    def process_request_2(self, rp, request, spider):
        if rp is not None and not rp.can_fetch(
                 to_native_str(self._useragent), request.url):
            logger.debug("Forbidden by robots.txt: %(request)s",
                         {'request': request}, extra={'spider': spider})
            raise IgnoreRequest()

    def robot_parser(self, request, spider):
        url = urlparse_cached(request)
        netloc = url.netloc

        if netloc not in self._parsers:
            self._parsers[netloc] = Deferred()
            robotsurl = "%s://%s/robots.txt" % (url.scheme, url.netloc)
            robotsreq = Request(
                robotsurl,
                priority=self.DOWNLOAD_PRIORITY,
                meta={'dont_obey_robotstxt': True}
            )
            dfd = self.crawler.engine.download(robotsreq, spider)
            dfd.addCallback(self._parse_robots, netloc)
            dfd.addErrback(self._logerror, robotsreq, spider)
            dfd.addErrback(self._robots_error, netloc)

        if isinstance(self._parsers[netloc], Deferred):
            d = Deferred()
            def cb(result):
                d.callback(result)
                return result
            self._parsers[netloc].addCallback(cb)
            return d
        else:
            return self._parsers[netloc]

    def _logerror(self, failure, request, spider):
        if failure.type is not IgnoreRequest:
            logger.error("Error downloading %(request)s: %(f_exception)s",
                         {'request': request, 'f_exception': failure.value},
                         exc_info=failure_to_exc_info(failure),
                         extra={'spider': spider})
        return failure

    def _parse_robots(self, response, netloc):
        rp = robotparser.RobotFileParser(response.url)
        body = ''
        if hasattr(response, 'text'):
            body = response.text
        else: # last effort try
            try:
                body = response.body.decode('utf-8')
            except UnicodeDecodeError:
                # If we found garbage, disregard it:,
                # but keep the lookup cached (in self._parsers)
                # Running rp.parse() will set rp state from
                # 'disallow all' to 'allow any'.
                pass
        # stdlib's robotparser expects native 'str' ;
        # with unicode input, non-ASCII encoded bytes decoding fails in Python2
        rp.parse(to_native_str(body).splitlines())

        rp_dfd = self._parsers[netloc]
        self._parsers[netloc] = rp
        rp_dfd.callback(rp)

    def _robots_error(self, failure, netloc):
        rp_dfd = self._parsers[netloc]
        self._parsers[netloc] = None
        rp_dfd.callback(None)
