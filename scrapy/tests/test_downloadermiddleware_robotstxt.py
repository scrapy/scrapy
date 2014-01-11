import mock
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.trial import unittest
from scrapy.contrib.downloadermiddleware.robotstxt import RobotsTxtMiddleware
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Request, Response
from scrapy.settings import CrawlerSettings


class RobotsTxtMiddlewareTest(unittest.TestCase):

    def test(self):
        crawler = mock.MagicMock()
        crawler.settings = CrawlerSettings()
        crawler.settings.overrides['USER_AGENT'] = 'CustomAgent'
        crawler.settings.overrides['ROBOTSTXT_OBEY'] = True
        crawler.engine.download = mock.MagicMock()
        deferred = Deferred()
        crawler.engine.download.return_value = deferred
        ROBOTS = ''
        response = Response('http://site.local/robots.txt', body=ROBOTS)
        reactor.callLater(0, deferred.callback, response)
        middleware = RobotsTxtMiddleware(crawler)
        spider = None # Not actually used
        self.assertIsNone(middleware.process_request(Request('http://site.local/dummy'), spider))
        self.assertRaises(IgnoreRequest, middleware.process_request, Request('http://site.local/forbidden'), spider)