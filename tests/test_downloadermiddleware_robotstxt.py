from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest import mock

import pytest
from twisted.internet import error
from twisted.internet.defer import Deferred, DeferredList
from twisted.python import failure

from scrapy.downloadermiddlewares.robotstxt import RobotsTxtMiddleware
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request, Response, TextResponse
from scrapy.http.request import NO_CALLBACK
from scrapy.settings import Settings
from scrapy.utils.asyncio import call_later
from scrapy.utils.defer import (
    deferred_f_from_coro_f,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from tests.test_robotstxt_interface import rerp_available

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


class TestRobotsTxtMiddleware:
    def setup_method(self):
        self.crawler = mock.MagicMock()
        self.crawler.settings = Settings()
        self.crawler.engine.download_async = mock.AsyncMock()

    def teardown_method(self):
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

        async def return_response(request):
            deferred = Deferred()
            call_later(0, deferred.callback, response)
            return await maybe_deferred_to_future(deferred)

        crawler.engine.download_async.side_effect = return_response
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
    async def test_robotstxt_multiple_reqs(self) -> None:
        middleware = RobotsTxtMiddleware(self._get_successful_crawler())
        d1 = deferred_from_coro(
            middleware.process_request(Request("http://site.local/allowed1"))
        )
        d2 = deferred_from_coro(
            middleware.process_request(Request("http://site.local/allowed2"))
        )
        await maybe_deferred_to_future(DeferredList([d1, d2], fireOnOneErrback=True))

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_robotstxt_multiple_reqs_asyncio(self) -> None:
        middleware = RobotsTxtMiddleware(self._get_successful_crawler())
        c1 = middleware.process_request(Request("http://site.local/allowed1"))
        c2 = middleware.process_request(Request("http://site.local/allowed2"))
        await asyncio.gather(c1, c2)

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

        async def return_response(request):
            deferred = Deferred()
            call_later(0, deferred.callback, response)
            return await maybe_deferred_to_future(deferred)

        crawler.engine.download_async.side_effect = return_response
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

        async def return_response(request):
            deferred = Deferred()
            call_later(0, deferred.callback, response)
            return await maybe_deferred_to_future(deferred)

        crawler.engine.download_async.side_effect = return_response
        return crawler

    @deferred_f_from_coro_f
    async def test_robotstxt_empty_response(self):
        # empty response should equal 'allow all'
        middleware = RobotsTxtMiddleware(self._get_emptybody_crawler())
        await self.assertNotIgnored(Request("http://site.local/allowed"), middleware)
        await self.assertNotIgnored(Request("http://site.local/admin/main"), middleware)
        await self.assertNotIgnored(Request("http://site.local/static/"), middleware)

    @deferred_f_from_coro_f
    async def test_robotstxt_error(self, caplog: pytest.LogCaptureFixture) -> None:
        self.crawler.settings.set("ROBOTSTXT_OBEY", True)
        err = error.DNSLookupError("Robotstxt address not found")

        async def return_failure(request):
            deferred = Deferred()
            call_later(0, deferred.errback, failure.Failure(err))
            return await maybe_deferred_to_future(deferred)

        self.crawler.engine.download_async.side_effect = return_failure

        middleware = RobotsTxtMiddleware(self.crawler)
        await middleware.process_request(Request("http://site.local"))
        assert "DNS lookup failed: Robotstxt address not found" in caplog.text

    @deferred_f_from_coro_f
    async def test_robotstxt_immediate_error(self):
        self.crawler.settings.set("ROBOTSTXT_OBEY", True)
        err = error.DNSLookupError("Robotstxt address not found")

        async def immediate_failure(request):
            raise err

        self.crawler.engine.download_async.side_effect = immediate_failure

        middleware = RobotsTxtMiddleware(self.crawler)
        await self.assertNotIgnored(Request("http://site.local"), middleware)

    @deferred_f_from_coro_f
    async def test_ignore_robotstxt_request(self):
        self.crawler.settings.set("ROBOTSTXT_OBEY", True)

        async def ignore_request(request):
            deferred = Deferred()
            call_later(0, deferred.errback, failure.Failure(IgnoreRequest()))
            return await maybe_deferred_to_future(deferred)

        self.crawler.engine.download_async.side_effect = ignore_request

        middleware = RobotsTxtMiddleware(self.crawler)
        with mock.patch(
            "scrapy.downloadermiddlewares.robotstxt.logger"
        ) as mw_module_logger:
            await self.assertNotIgnored(
                Request("http://site.local/allowed"), middleware
            )
            assert not mw_module_logger.error.called

    def test_robotstxt_user_agent_setting(self):
        crawler = self._get_successful_crawler()
        crawler.settings.set("ROBOTSTXT_USER_AGENT", "Examplebot")
        crawler.settings.set("USER_AGENT", "Mozilla/5.0 (X11; Linux x86_64)")
        middleware = RobotsTxtMiddleware(crawler)
        rp = mock.MagicMock(return_value=True)
        middleware.process_request_2(rp, Request("http://site.local/allowed"))
        rp.allowed.assert_called_once_with("http://site.local/allowed", "Examplebot")

    @deferred_f_from_coro_f
    async def test_robotstxt_local_file(self):
        middleware = RobotsTxtMiddleware(self._get_emptybody_crawler())
        middleware.process_request_2 = mock.MagicMock()

        await middleware.process_request(Request("data:text/plain,Hello World data"))
        assert not middleware.process_request_2.called

        await middleware.process_request(
            Request("file:///tests/sample_data/test_site/nothinghere.html")
        )
        assert not middleware.process_request_2.called

        await middleware.process_request(Request("http://site.local/allowed"))
        assert middleware.process_request_2.called

    async def assertNotIgnored(
        self, request: Request, middleware: RobotsTxtMiddleware
    ) -> None:
        try:
            await middleware.process_request(request)
        except IgnoreRequest:
            pytest.fail("IgnoreRequest was raised unexpectedly")

    async def assertIgnored(
        self, request: Request, middleware: RobotsTxtMiddleware
    ) -> None:
        with pytest.raises(IgnoreRequest):
            await middleware.process_request(request)

    def assertRobotsTxtRequested(self, base_url: str) -> None:
        calls = self.crawler.engine.download_async.call_args_list
        request = calls[0][0][0]
        assert request.url == f"{base_url}/robots.txt"
        assert request.callback == NO_CALLBACK


@pytest.mark.skipif(not rerp_available(), reason="Rerp parser is not installed")
class TestRobotsTxtMiddlewareWithRerp(TestRobotsTxtMiddleware):
    def setup_method(self):
        super().setup_method()
        self.crawler.settings.set(
            "ROBOTSTXT_PARSER", "scrapy.robotstxt.RerpRobotParser"
        )
