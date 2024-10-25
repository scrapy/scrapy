from unittest import mock

from twisted.internet import error, reactor
from twisted.internet.defer import Deferred, DeferredList, maybeDeferred
from twisted.python import failure
from twisted.trial import unittest

from scrapy.downloadermiddlewares.robotstxt import RobotsTxtMiddleware
from scrapy.downloadermiddlewares.robotstxt import logger as mw_module_logger
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request, Response, TextResponse
from scrapy.http.request import NO_CALLBACK
from scrapy.settings import Settings
from tests.test_robotstxt_interface import rerp_available


class RobotsTxtMiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.crawler = mock.MagicMock()
        self.crawler.settings = Settings()
        self.crawler.engine.download = mock.MagicMock()

    def tearDown(self):
        del self.crawler

    def test_robotstxt_settings(self):
        self.crawler.settings = Settings()
        self.crawler.settings.set("USER_AGENT", "CustomAgent")
        self.assertRaises(NotConfigured, RobotsTxtMiddleware, self.crawler)

    def _get_successful_crawler(self):
        crawler = self.crawler
        crawler.settings.set("ROBOTSTXT_OBEY", True)
        ROBOTS = """
User-Agent: *
Disallow: /admin/
Disallow: /static/
# taken from https://en.wikipedia.org/robots.txt
Disallow: /wiki/K%C3%A4ytt%C3%A4j%C3%A4:
Disallow: /wiki/Käyttäjä:
User-Agent: UnicödeBöt
Disallow: /some/randome/page.html
""".encode()
        response = TextResponse("http://site.local/robots.txt", body=ROBOTS)

        def return_response(request):
            deferred = Deferred()
            reactor.callFromThread(deferred.callback, response)
            return deferred

        crawler.engine.download.side_effect = return_response
        return crawler

    def test_robotstxt(self):
        middleware = RobotsTxtMiddleware(self._get_successful_crawler())
        return DeferredList(
            [
                self.assertNotIgnored(Request("http://site.local/allowed"), middleware),
                maybeDeferred(self.assertRobotsTxtRequested, "http://site.local"),
                self.assertIgnored(Request("http://site.local/admin/main"), middleware),
                self.assertIgnored(Request("http://site.local/static/"), middleware),
                self.assertIgnored(
                    Request("http://site.local/wiki/K%C3%A4ytt%C3%A4j%C3%A4:"),
                    middleware,
                ),
                self.assertIgnored(
                    Request("http://site.local/wiki/Käyttäjä:"), middleware
                ),
            ],
            fireOnOneErrback=True,
        )

    def test_robotstxt_ready_parser(self):
        middleware = RobotsTxtMiddleware(self._get_successful_crawler())
        d = self.assertNotIgnored(Request("http://site.local/allowed"), middleware)
        d.addCallback(
            lambda _: self.assertNotIgnored(
                Request("http://site.local/allowed"), middleware
            )
        )
        return d

    def test_robotstxt_meta(self):
        middleware = RobotsTxtMiddleware(self._get_successful_crawler())
        meta = {"dont_obey_robotstxt": True}
        return DeferredList(
            [
                self.assertNotIgnored(
                    Request("http://site.local/allowed", meta=meta), middleware
                ),
                self.assertNotIgnored(
                    Request("http://site.local/admin/main", meta=meta), middleware
                ),
                self.assertNotIgnored(
                    Request("http://site.local/static/", meta=meta), middleware
                ),
            ],
            fireOnOneErrback=True,
        )

    def _get_garbage_crawler(self):
        crawler = self.crawler
        crawler.settings.set("ROBOTSTXT_OBEY", True)
        response = Response(
            "http://site.local/robots.txt", body=b"GIF89a\xd3\x00\xfe\x00\xa2"
        )

        def return_response(request):
            deferred = Deferred()
            reactor.callFromThread(deferred.callback, response)
            return deferred

        crawler.engine.download.side_effect = return_response
        return crawler

    def test_robotstxt_garbage(self):
        # garbage response should be discarded, equal 'allow all'
        middleware = RobotsTxtMiddleware(self._get_garbage_crawler())
        deferred = DeferredList(
            [
                self.assertNotIgnored(Request("http://site.local"), middleware),
                self.assertNotIgnored(Request("http://site.local/allowed"), middleware),
                self.assertNotIgnored(
                    Request("http://site.local/admin/main"), middleware
                ),
                self.assertNotIgnored(Request("http://site.local/static/"), middleware),
            ],
            fireOnOneErrback=True,
        )
        return deferred

    def _get_emptybody_crawler(self):
        crawler = self.crawler
        crawler.settings.set("ROBOTSTXT_OBEY", True)
        response = Response("http://site.local/robots.txt")

        def return_response(request):
            deferred = Deferred()
            reactor.callFromThread(deferred.callback, response)
            return deferred

        crawler.engine.download.side_effect = return_response
        return crawler

    def test_robotstxt_empty_response(self):
        # empty response should equal 'allow all'
        middleware = RobotsTxtMiddleware(self._get_emptybody_crawler())
        return DeferredList(
            [
                self.assertNotIgnored(Request("http://site.local/allowed"), middleware),
                self.assertNotIgnored(
                    Request("http://site.local/admin/main"), middleware
                ),
                self.assertNotIgnored(Request("http://site.local/static/"), middleware),
            ],
            fireOnOneErrback=True,
        )

    def test_robotstxt_error(self):
        self.crawler.settings.set("ROBOTSTXT_OBEY", True)
        err = error.DNSLookupError("Robotstxt address not found")

        def return_failure(request):
            deferred = Deferred()
            reactor.callFromThread(deferred.errback, failure.Failure(err))
            return deferred

        self.crawler.engine.download.side_effect = return_failure

        middleware = RobotsTxtMiddleware(self.crawler)
        middleware._logerror = mock.MagicMock(side_effect=middleware._logerror)
        deferred = middleware.process_request(Request("http://site.local"), None)
        deferred.addCallback(lambda _: self.assertTrue(middleware._logerror.called))
        return deferred

    def test_robotstxt_immediate_error(self):
        self.crawler.settings.set("ROBOTSTXT_OBEY", True)
        err = error.DNSLookupError("Robotstxt address not found")

        def immediate_failure(request):
            deferred = Deferred()
            deferred.errback(failure.Failure(err))
            return deferred

        self.crawler.engine.download.side_effect = immediate_failure

        middleware = RobotsTxtMiddleware(self.crawler)
        return self.assertNotIgnored(Request("http://site.local"), middleware)

    def test_ignore_robotstxt_request(self):
        self.crawler.settings.set("ROBOTSTXT_OBEY", True)

        def ignore_request(request):
            deferred = Deferred()
            reactor.callFromThread(deferred.errback, failure.Failure(IgnoreRequest()))
            return deferred

        self.crawler.engine.download.side_effect = ignore_request

        middleware = RobotsTxtMiddleware(self.crawler)
        mw_module_logger.error = mock.MagicMock()

        d = self.assertNotIgnored(Request("http://site.local/allowed"), middleware)
        d.addCallback(lambda _: self.assertFalse(mw_module_logger.error.called))
        return d

    def test_robotstxt_user_agent_setting(self):
        crawler = self._get_successful_crawler()
        crawler.settings.set("ROBOTSTXT_USER_AGENT", "Examplebot")
        crawler.settings.set("USER_AGENT", "Mozilla/5.0 (X11; Linux x86_64)")
        middleware = RobotsTxtMiddleware(crawler)
        rp = mock.MagicMock(return_value=True)
        middleware.process_request_2(rp, Request("http://site.local/allowed"), None)
        rp.allowed.assert_called_once_with("http://site.local/allowed", "Examplebot")

    def test_robotstxt_local_file(self):
        middleware = RobotsTxtMiddleware(self._get_emptybody_crawler())
        assert not middleware.process_request(
            Request("data:text/plain,Hello World data"), None
        )
        assert not middleware.process_request(
            Request("file:///tests/sample_data/test_site/nothinghere.html"), None
        )
        assert isinstance(
            middleware.process_request(Request("http://site.local/allowed"), None),
            Deferred,
        )

    def assertNotIgnored(self, request, middleware):
        spider = None  # not actually used
        dfd = maybeDeferred(middleware.process_request, request, spider)
        dfd.addCallback(self.assertIsNone)
        return dfd

    def assertIgnored(self, request, middleware):
        spider = None  # not actually used
        return self.assertFailure(
            maybeDeferred(middleware.process_request, request, spider), IgnoreRequest
        )

    def assertRobotsTxtRequested(self, base_url):
        calls = self.crawler.engine.download.call_args_list
        request = calls[0][0][0]
        self.assertEqual(request.url, f"{base_url}/robots.txt")
        self.assertEqual(request.callback, NO_CALLBACK)


class RobotsTxtMiddlewareWithRerpTest(RobotsTxtMiddlewareTest):
    if not rerp_available():
        skip = "Rerp parser is not installed"

    def setUp(self):
        super().setUp()
        self.crawler.settings.set(
            "ROBOTSTXT_PARSER", "scrapy.robotstxt.RerpRobotParser"
        )
