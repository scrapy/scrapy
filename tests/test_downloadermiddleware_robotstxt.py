from __future__ import annotations

from typing import TYPE_CHECKING
from unittest import mock

import pytest
from twisted.internet import error, reactor
from twisted.internet.defer import Deferred, maybeDeferred
from twisted.python import failure
from twisted.trial import unittest

from scrapy.downloadermiddlewares.robotstxt import RobotsTxtMiddleware
from scrapy.downloadermiddlewares.robotstxt import logger as mw_module_logger
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request, Response, TextResponse
from scrapy.http.request import NO_CALLBACK
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from tests.test_robotstxt_interface import rerp_available

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


class TestRobotsTxtMiddleware(unittest.TestCase):
    def setUp(self):
        self.crawler = mock.MagicMock()
        self.crawler.settings = Settings()
        self.crawler.engine.download = mock.MagicMock()

    def tearDown(self):
        del self.crawler

    def test_robotstxt_settings(self):
        self.crawler.settings = Settings()
        self.crawler.settings.set("USER_AGENT", "CustomAgent")
        with pytest.raises(NotConfigured):
            RobotsTxtMiddleware(self.crawler)

    def _get_successful_crawler(self) -> Crawler:
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

    @deferred_f_from_coro_f
    async def test_robotstxt(self):
        middleware = RobotsTxtMiddleware(self._get_successful_crawler())
        await self.assertNotIgnored(Request("http://site.local/allowed"), middleware)
        self.assertRobotsTxtRequested("http://site.local")
        await self.assertIgnored(Request("http://site.local/admin/main"), middleware)
        await self.assertIgnored(Request("http://site.local/static/"), middleware)
        await self.assertIgnored(
            Request("http://site.local/wiki/K%C3%A4ytt%C3%A4j%C3%A4:"), middleware
        )
        await self.assertIgnored(
            Request("http://site.local/wiki/Käyttäjä:"), middleware
        )

    @deferred_f_from_coro_f
    async def test_robotstxt_ready_parser(self):
        middleware = RobotsTxtMiddleware(self._get_successful_crawler())
        await self.assertNotIgnored(Request("http://site.local/allowed"), middleware)
        await self.assertNotIgnored(Request("http://site.local/allowed"), middleware)

    @deferred_f_from_coro_f
    async def test_robotstxt_meta(self):
        middleware = RobotsTxtMiddleware(self._get_successful_crawler())
        meta = {"dont_obey_robotstxt": True}
        await self.assertNotIgnored(
            Request("http://site.local/allowed", meta=meta), middleware
        )
        await self.assertNotIgnored(
            Request("http://site.local/admin/main", meta=meta), middleware
        )
        await self.assertNotIgnored(
            Request("http://site.local/static/", meta=meta), middleware
        )

    def _get_garbage_crawler(self) -> Crawler:
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

    @deferred_f_from_coro_f
    async def test_robotstxt_garbage(self):
        # garbage response should be discarded, equal 'allow all'
        middleware = RobotsTxtMiddleware(self._get_garbage_crawler())
        await self.assertNotIgnored(Request("http://site.local"), middleware)
        await self.assertNotIgnored(Request("http://site.local/allowed"), middleware)
        await self.assertNotIgnored(Request("http://site.local/admin/main"), middleware)
        await self.assertNotIgnored(Request("http://site.local/static/"), middleware)

    def _get_emptybody_crawler(self) -> Crawler:
        crawler = self.crawler
        crawler.settings.set("ROBOTSTXT_OBEY", True)
        response = Response("http://site.local/robots.txt")

        def return_response(request):
            deferred = Deferred()
            reactor.callFromThread(deferred.callback, response)
            return deferred

        crawler.engine.download.side_effect = return_response
        return crawler

    @deferred_f_from_coro_f
    async def test_robotstxt_empty_response(self):
        # empty response should equal 'allow all'
        middleware = RobotsTxtMiddleware(self._get_emptybody_crawler())
        await self.assertNotIgnored(Request("http://site.local/allowed"), middleware)
        await self.assertNotIgnored(Request("http://site.local/admin/main"), middleware)
        await self.assertNotIgnored(Request("http://site.local/static/"), middleware)

    @deferred_f_from_coro_f
    async def test_robotstxt_error(self):
        self.crawler.settings.set("ROBOTSTXT_OBEY", True)
        err = error.DNSLookupError("Robotstxt address not found")

        def return_failure(request):
            deferred = Deferred()
            reactor.callFromThread(deferred.errback, failure.Failure(err))
            return deferred

        self.crawler.engine.download.side_effect = return_failure

        middleware = RobotsTxtMiddleware(self.crawler)
        middleware._logerror = mock.MagicMock(side_effect=middleware._logerror)
        await maybe_deferred_to_future(
            middleware.process_request(Request("http://site.local"), None)
        )
        assert middleware._logerror.called

    @deferred_f_from_coro_f
    async def test_robotstxt_immediate_error(self):
        self.crawler.settings.set("ROBOTSTXT_OBEY", True)
        err = error.DNSLookupError("Robotstxt address not found")

        def immediate_failure(request):
            deferred = Deferred()
            deferred.errback(failure.Failure(err))
            return deferred

        self.crawler.engine.download.side_effect = immediate_failure

        middleware = RobotsTxtMiddleware(self.crawler)
        await self.assertNotIgnored(Request("http://site.local"), middleware)

    @deferred_f_from_coro_f
    async def test_ignore_robotstxt_request(self):
        self.crawler.settings.set("ROBOTSTXT_OBEY", True)

        def ignore_request(request):
            deferred = Deferred()
            reactor.callFromThread(deferred.errback, failure.Failure(IgnoreRequest()))
            return deferred

        self.crawler.engine.download.side_effect = ignore_request

        middleware = RobotsTxtMiddleware(self.crawler)
        mw_module_logger.error = mock.MagicMock()

        await self.assertNotIgnored(Request("http://site.local/allowed"), middleware)
        assert not mw_module_logger.error.called  # type: ignore[attr-defined]

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

    async def assertNotIgnored(
        self, request: Request, middleware: RobotsTxtMiddleware
    ) -> None:
        spider = None  # not actually used
        result = await maybe_deferred_to_future(
            maybeDeferred(middleware.process_request, request, spider)  # type: ignore[call-overload]
        )
        assert result is None

    async def assertIgnored(
        self, request: Request, middleware: RobotsTxtMiddleware
    ) -> None:
        spider = None  # not actually used
        await maybe_deferred_to_future(
            self.assertFailure(
                middleware.process_request(request, spider),  # type: ignore[arg-type]
                IgnoreRequest,
            )
        )

    def assertRobotsTxtRequested(self, base_url: str) -> None:
        calls = self.crawler.engine.download.call_args_list
        request = calls[0][0][0]
        assert request.url == f"{base_url}/robots.txt"
        assert request.callback == NO_CALLBACK


class TestRobotsTxtMiddlewareWithRerp(TestRobotsTxtMiddleware):
    if not rerp_available():
        skip = "Rerp parser is not installed"

    def setUp(self):
        super().setUp()
        self.crawler.settings.set(
            "ROBOTSTXT_PARSER", "scrapy.robotstxt.RerpRobotParser"
        )
