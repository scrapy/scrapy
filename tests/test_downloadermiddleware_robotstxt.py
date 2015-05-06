from __future__ import absolute_import
import re
from twisted.internet import reactor, error
from twisted.internet.defer import Deferred
from twisted.python import failure
from twisted.trial import unittest
from scrapy.downloadermiddlewares.robotstxt import RobotsTxtMiddleware
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request, Response
from scrapy.settings import Settings
from tests import mock


class RobotsTxtMiddlewareTest(unittest.TestCase):

    def test_robotstxt(self):
        middleware = self._get_middleware()
        # There is a bit of neglect in robotstxt.py: robots.txt is fetched asynchronously,
        # and it is actually fetched only *after* first process_request completes.
        # So, first process_request will always succeed.
        # We defer test() because otherwise robots.txt download mock will be called after assertRaises failure.
        self.assertNotIgnored(Request('http://site.local'), middleware)
        def test(r):
            self.assertNotIgnored(Request('http://site.local/allowed'), middleware)
            self.assertIgnored(Request('http://site.local/admin/main'), middleware)
            self.assertIgnored(Request('http://site.local/static/'), middleware)
        deferred = Deferred()
        deferred.addCallback(test)
        reactor.callFromThread(deferred.callback, None)
        return deferred

    def test_robotstxt_meta(self):
        meta = {'dont_obey_robotstxt': True}
        middleware = self._get_middleware()
        self.assertNotIgnored(Request('http://site.local', meta=meta), middleware)
        def test(r):
            self.assertNotIgnored(Request('http://site.local/allowed', meta=meta), middleware)
            self.assertNotIgnored(Request('http://site.local/admin/main', meta=meta), middleware)
            self.assertNotIgnored(Request('http://site.local/static/', meta=meta), middleware)
        deferred = Deferred()
        deferred.addCallback(test)
        reactor.callFromThread(deferred.callback, None)
        return deferred

    def test_robotstxt_error(self):
        crawler = mock.MagicMock()
        crawler.settings = Settings()
        crawler.settings.set('ROBOTSTXT_OBEY', True)
        crawler.engine.download = mock.MagicMock()
        err = error.DNSLookupError('Robotstxt address not found')
        def return_failure(request, spider):
            deferred = Deferred()
            reactor.callFromThread(deferred.errback, failure.Failure(err))
            return deferred
        crawler.engine.download.side_effect = return_failure

        middleware = RobotsTxtMiddleware(crawler)
        middleware._logerror = mock.MagicMock()
        middleware.process_request(Request('http://site.local'), None)
        deferred = Deferred()
        deferred.addErrback(lambda _: self.assertIsNone(middleware._logerror.assert_any_call()))
        reactor.callFromThread(deferred.callback, None)
        return deferred

    def assertNotIgnored(self, request, middleware):
        spider = None  # not actually used
        self.assertIsNone(middleware.process_request(request, spider))

    def assertIgnored(self, request, middleware):
        spider = None  # not actually used
        self.assertRaises(IgnoreRequest, middleware.process_request, request, spider)

    def _get_crawler(self):
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
        return crawler

    def _get_middleware(self):
        crawler = self._get_crawler()
        return RobotsTxtMiddleware(crawler)
