# -*- coding: utf-8 -*-
from unittest import mock

from twisted.internet import reactor, error
from twisted.internet.defer import Deferred, DeferredList, maybeDeferred
from twisted.python import failure
from twisted.trial import unittest
from scrapy.downloadermiddlewares.robotstxt import (RobotsTxtMiddleware,
                                                    logger as mw_module_logger)
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request, Response, TextResponse
from scrapy.settings import Settings
from tests.test_robotstxt_interface import rerp_available, reppy_available


class RobotsTxtMiddlewareTest(unittest.TestCase):

    def setUp(self):
        self.crawler = mock.MagicMock()
        self.crawler.settings = Settings()
        self.crawler.engine.download = mock.MagicMock()

    def tearDown(self):
        del self.crawler

    def test_robotstxt_settings(self):
        self.crawler.settings = Settings()
        self.crawler.settings.set('USER_AGENT', 'CustomAgent')
        self.assertRaises(NotConfigured, RobotsTxtMiddleware, self.crawler)

    def _get_successful_crawler(self):
        crawler = self.crawler
        crawler.settings.set('ROBOTSTXT_OBEY', True)
        ROBOTS = u"""
User-Agent: *
Disallow: /admin/
Disallow: /static/
# taken from https://en.wikipedia.org/robots.txt
Disallow: /wiki/K%C3%A4ytt%C3%A4j%C3%A4:
Disallow: /wiki/Käyttäjä:
User-Agent: UnicödeBöt
Disallow: /some/randome/page.html
""".encode('utf-8')
        response = TextResponse('http://site.local/robots.txt', body=ROBOTS)

        def return_response(request, spider):
            deferred = Deferred()
            reactor.callFromThread(deferred.callback, response)
            return deferred
        crawler.engine.download.side_effect = return_response
        return crawler

    def test_robotstxt(self):
        middleware = RobotsTxtMiddleware(self._get_successful_crawler())
        return DeferredList([
            self.assertNotIgnored(Request('http://site.local/allowed'), middleware),
            self.assertIgnored(Request('http://site.local/admin/main'), middleware),
            self.assertIgnored(Request('http://site.local/static/'), middleware),
            self.assertIgnored(Request('http://site.local/wiki/K%C3%A4ytt%C3%A4j%C3%A4:'), middleware),
            self.assertIgnored(Request(u'http://site.local/wiki/Käyttäjä:'), middleware)
        ], fireOnOneErrback=True)

    def test_robotstxt_ready_parser(self):
        middleware = RobotsTxtMiddleware(self._get_successful_crawler())
        d = self.assertNotIgnored(Request('http://site.local/allowed'), middleware)
        d.addCallback(lambda _: self.assertNotIgnored(Request('http://site.local/allowed'), middleware))
        return d

    def test_robotstxt_meta(self):
        middleware = RobotsTxtMiddleware(self._get_successful_crawler())
        meta = {'dont_obey_robotstxt': True}
        return DeferredList([
            self.assertNotIgnored(Request('http://site.local/allowed', meta=meta), middleware),
            self.assertNotIgnored(Request('http://site.local/admin/main', meta=meta), middleware),
            self.assertNotIgnored(Request('http://site.local/static/', meta=meta), middleware)
        ], fireOnOneErrback=True)

    def _get_garbage_crawler(self):
        crawler = self.crawler
        crawler.settings.set('ROBOTSTXT_OBEY', True)
        response = Response('http://site.local/robots.txt', body=b'GIF89a\xd3\x00\xfe\x00\xa2')

        def return_response(request, spider):
            deferred = Deferred()
            reactor.callFromThread(deferred.callback, response)
            return deferred
        crawler.engine.download.side_effect = return_response
        return crawler

    def test_robotstxt_garbage(self):
        # garbage response should be discarded, equal 'allow all'
        middleware = RobotsTxtMiddleware(self._get_garbage_crawler())
        deferred = DeferredList([
            self.assertNotIgnored(Request('http://site.local'), middleware),
            self.assertNotIgnored(Request('http://site.local/allowed'), middleware),
            self.assertNotIgnored(Request('http://site.local/admin/main'), middleware),
            self.assertNotIgnored(Request('http://site.local/static/'), middleware)
        ], fireOnOneErrback=True)
        return deferred

    def _get_emptybody_crawler(self):
        crawler = self.crawler
        crawler.settings.set('ROBOTSTXT_OBEY', True)
        response = Response('http://site.local/robots.txt')

        def return_response(request, spider):
            deferred = Deferred()
            reactor.callFromThread(deferred.callback, response)
            return deferred
        crawler.engine.download.side_effect = return_response
        return crawler

    def test_robotstxt_empty_response(self):
        # empty response should equal 'allow all'
        middleware = RobotsTxtMiddleware(self._get_emptybody_crawler())
        return DeferredList([
            self.assertNotIgnored(Request('http://site.local/allowed'), middleware),
            self.assertNotIgnored(Request('http://site.local/admin/main'), middleware),
            self.assertNotIgnored(Request('http://site.local/static/'), middleware)
        ], fireOnOneErrback=True)

    def test_robotstxt_error(self):
        self.crawler.settings.set('ROBOTSTXT_OBEY', True)
        err = error.DNSLookupError('Robotstxt address not found')

        def return_failure(request, spider):
            deferred = Deferred()
            reactor.callFromThread(deferred.errback, failure.Failure(err))
            return deferred
        self.crawler.engine.download.side_effect = return_failure

        middleware = RobotsTxtMiddleware(self.crawler)
        middleware._logerror = mock.MagicMock(side_effect=middleware._logerror)
        deferred = middleware.process_request(Request('http://site.local'), None)
        deferred.addCallback(lambda _: self.assertTrue(middleware._logerror.called))
        return deferred

    def test_robotstxt_immediate_error(self):
        self.crawler.settings.set('ROBOTSTXT_OBEY', True)
        err = error.DNSLookupError('Robotstxt address not found')

        def immediate_failure(request, spider):
            deferred = Deferred()
            deferred.errback(failure.Failure(err))
            return deferred
        self.crawler.engine.download.side_effect = immediate_failure

        middleware = RobotsTxtMiddleware(self.crawler)
        return self.assertNotIgnored(Request('http://site.local'), middleware)

    def test_ignore_robotstxt_request(self):
        self.crawler.settings.set('ROBOTSTXT_OBEY', True)

        def ignore_request(request, spider):
            deferred = Deferred()
            reactor.callFromThread(deferred.errback, failure.Failure(IgnoreRequest()))
            return deferred
        self.crawler.engine.download.side_effect = ignore_request

        middleware = RobotsTxtMiddleware(self.crawler)
        mw_module_logger.error = mock.MagicMock()

        d = self.assertNotIgnored(Request('http://site.local/allowed'), middleware)
        d.addCallback(lambda _: self.assertFalse(mw_module_logger.error.called))
        return d

    def test_robotstxt_user_agent_setting(self):
        crawler = self._get_successful_crawler()
        crawler.settings.set('ROBOTSTXT_USER_AGENT', 'Examplebot')
        crawler.settings.set('USER_AGENT', 'Mozilla/5.0 (X11; Linux x86_64)')
        middleware = RobotsTxtMiddleware(crawler)
        rp = mock.MagicMock(return_value=True)
        middleware.process_request_2(rp, Request('http://site.local/allowed'), None)
        rp.allowed.assert_called_once_with('http://site.local/allowed', 'Examplebot')

    def assertNotIgnored(self, request, middleware):
        spider = None  # not actually used
        dfd = maybeDeferred(middleware.process_request, request, spider)
        dfd.addCallback(self.assertIsNone)
        return dfd

    def assertIgnored(self, request, middleware):
        spider = None  # not actually used
        return self.assertFailure(maybeDeferred(middleware.process_request, request, spider),
                                  IgnoreRequest)


class RobotsTxtMiddlewareWithRerpTest(RobotsTxtMiddlewareTest):
    if not rerp_available():
        skip = "Rerp parser is not installed"

    def setUp(self):
        super(RobotsTxtMiddlewareWithRerpTest, self).setUp()
        self.crawler.settings.set('ROBOTSTXT_PARSER', 'scrapy.robotstxt.RerpRobotParser')


class RobotsTxtMiddlewareWithReppyTest(RobotsTxtMiddlewareTest):
    if not reppy_available():
        skip = "Reppy parser is not installed"

    def setUp(self):
        super(RobotsTxtMiddlewareWithReppyTest, self).setUp()
        self.crawler.settings.set('ROBOTSTXT_PARSER', 'scrapy.robotstxt.ReppyRobotParser')
