import re
import mock
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.trial import unittest
from scrapy.contrib.downloadermiddleware.robotstxt import RobotsTxtMiddleware
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request, Response
from scrapy.settings import Settings


class RobotsTxtMiddlewareTest(unittest.TestCase):

    def test(self):
        crawler = mock.MagicMock()
        crawler.settings = Settings()
        crawler.settings.set('USER_AGENT', 'CustomAgent')
        self.assertRaises(NotConfigured, RobotsTxtMiddleware, crawler)
        crawler.settings.set('ROBOTSTXT_OBEY', True)
        crawler.engine.download = mock.MagicMock()
        ROBOTS = re.sub(r'^\s+(?m)', '', '''
        User-Agent: *
        Disallow: /admin/
        Disallow: /static/
        ''')
        response = Response('http://site.local/robots.txt', body=ROBOTS)
        def return_response(request, spider):
            deferred = Deferred()
            reactor.callFromThread(deferred.callback, response)
            return deferred
        crawler.engine.download.side_effect = return_response
        middleware = RobotsTxtMiddleware(crawler)
        spider = None  # not actually used
        # There is a bit of neglect in robotstxt.py: robots.txt is fetched asynchronously,
        # and it is actually fetched only *after* first process_request completes.
        # So, first process_request will always succeed.
        # We defer test() because otherwise robots.txt download mock will be called after assertRaises failure.
        self.assertIsNone(middleware.process_request(Request('http://site.local'), spider))  # not affected by robots.txt
        def test(r):
            self.assertIsNone(middleware.process_request(Request('http://site.local/allowed'), spider))
            self.assertRaises(IgnoreRequest, middleware.process_request, Request('http://site.local/admin/main'), spider)
            self.assertRaises(IgnoreRequest, middleware.process_request, Request('http://site.local/static/'), spider)
        deferred = Deferred()
        deferred.addCallback(test)
        reactor.callFromThread(deferred.callback, None)
        return deferred
