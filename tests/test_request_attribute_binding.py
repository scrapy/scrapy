from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scrapy import Request, signals
from scrapy.http.response import Response
from scrapy.utils.test import get_crawler
from tests.spiders import SingleRequestSpider
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    import pytest

    from tests.mockserver.http import MockServer

OVERRIDDEN_URL = "https://example.org"


class ProcessResponseMiddleware:
    def process_response(self, request, response):
        return response.replace(request=Request(OVERRIDDEN_URL))


class RaiseExceptionRequestMiddleware:
    def process_request(self, request):
        1 / 0
        return request


class CatchExceptionOverrideRequestMiddleware:
    def process_exception(self, request, exception):
        return Response(
            url="http://localhost/",
            body=b"Caught " + exception.__class__.__name__.encode("utf-8"),
            request=Request(OVERRIDDEN_URL),
        )


class CatchExceptionDoNotOverrideRequestMiddleware:
    def process_exception(self, request, exception):
        return Response(
            url="http://localhost/",
            body=b"Caught " + exception.__class__.__name__.encode("utf-8"),
        )


class AlternativeCallbacksSpider(SingleRequestSpider):
    name = "alternative_callbacks_spider"

    def alt_callback(self, response, foo=None):
        self.logger.info("alt_callback was invoked with foo=%s", foo)


class AlternativeCallbacksMiddleware:
    def __init__(self, crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_response(self, request, response):
        new_request = request.replace(
            url=OVERRIDDEN_URL,
            callback=self.crawler.spider.alt_callback,
            cb_kwargs={"foo": "bar"},
        )
        return response.replace(request=new_request)


class TestCrawl:
    @coroutine_test
    async def test_response_200(self, mockserver: MockServer) -> None:
        url = mockserver.url("/status?n=200")
        crawler = get_crawler(SingleRequestSpider)
        await crawler.crawl_async(seed=url, mockserver=mockserver)
        assert isinstance(crawler.spider, SingleRequestSpider)
        response = crawler.spider.meta["responses"][0]
        assert response.request.url == url

    @coroutine_test
    async def test_response_error(self, mockserver: MockServer) -> None:
        for status in ("404", "500"):
            url = mockserver.url(f"/status?n={status}")
            crawler = get_crawler(SingleRequestSpider)
            await crawler.crawl_async(seed=url, mockserver=mockserver)
            assert isinstance(crawler.spider, SingleRequestSpider)
            failure = crawler.spider.meta["failure"]
            response = failure.value.response
            assert failure.request.url == url
            assert response.request.url == url

    @coroutine_test
    async def test_downloader_middleware_raise_exception(
        self, mockserver: MockServer
    ) -> None:
        url = mockserver.url("/status?n=200")
        crawler = get_crawler(
            SingleRequestSpider,
            {
                "DOWNLOADER_MIDDLEWARES": {
                    RaiseExceptionRequestMiddleware: 590,
                },
            },
        )
        await crawler.crawl_async(seed=url, mockserver=mockserver)
        assert isinstance(crawler.spider, SingleRequestSpider)
        failure = crawler.spider.meta["failure"]
        assert failure.request.url == url
        assert isinstance(failure.value, ZeroDivisionError)

    @coroutine_test
    async def test_downloader_middleware_override_request_in_process_response(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        """
        Downloader middleware which returns a response with an specific 'request' attribute.

        * The spider callback should receive the overridden response.request
        * Handlers listening to the response_received signal should receive the overridden response.request
        * The "crawled" log message should show the overridden response.request
        """
        signal_params = {}

        def signal_handler(response, request, spider):
            signal_params["response"] = response
            signal_params["request"] = request

        url = mockserver.url("/status?n=200")
        crawler = get_crawler(
            SingleRequestSpider,
            {
                "DOWNLOADER_MIDDLEWARES": {
                    ProcessResponseMiddleware: 595,
                }
            },
        )
        crawler.signals.connect(signal_handler, signal=signals.response_received)

        with caplog.at_level(logging.DEBUG):
            await crawler.crawl_async(seed=url, mockserver=mockserver)

        assert isinstance(crawler.spider, SingleRequestSpider)
        response = crawler.spider.meta["responses"][0]
        assert response.request.url == OVERRIDDEN_URL

        assert signal_params["response"].url == url
        assert signal_params["request"].url == OVERRIDDEN_URL

        assert (
            "scrapy.core.engine",
            logging.DEBUG,
            f"Crawled (200) <GET {OVERRIDDEN_URL}> (referer: None)",
        ) in caplog.record_tuples

    @coroutine_test
    async def test_downloader_middleware_override_in_process_exception(
        self, mockserver: MockServer
    ) -> None:
        """
        An exception is raised but caught by the next middleware, which
        returns a Response with a specific 'request' attribute.

        The spider callback should receive the overridden response.request
        """
        url = mockserver.url("/status?n=200")
        crawler = get_crawler(
            SingleRequestSpider,
            {
                "DOWNLOADER_MIDDLEWARES": {
                    RaiseExceptionRequestMiddleware: 590,
                    CatchExceptionOverrideRequestMiddleware: 595,
                },
            },
        )
        await crawler.crawl_async(seed=url, mockserver=mockserver)
        assert isinstance(crawler.spider, SingleRequestSpider)
        response = crawler.spider.meta["responses"][0]
        assert response.body == b"Caught ZeroDivisionError"
        assert response.request.url == OVERRIDDEN_URL

    @coroutine_test
    async def test_downloader_middleware_do_not_override_in_process_exception(
        self, mockserver: MockServer
    ) -> None:
        """
        An exception is raised but caught by the next middleware, which
        returns a Response without a specific 'request' attribute.

        The spider callback should receive the original response.request
        """
        url = mockserver.url("/status?n=200")
        crawler = get_crawler(
            SingleRequestSpider,
            {
                "DOWNLOADER_MIDDLEWARES": {
                    RaiseExceptionRequestMiddleware: 590,
                    CatchExceptionDoNotOverrideRequestMiddleware: 595,
                },
            },
        )
        await crawler.crawl_async(seed=url, mockserver=mockserver)
        assert isinstance(crawler.spider, SingleRequestSpider)
        response = crawler.spider.meta["responses"][0]
        assert response.body == b"Caught ZeroDivisionError"
        assert response.request.url == url

    @coroutine_test
    async def test_downloader_middleware_alternative_callback(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        """
        Downloader middleware which returns a response with a
        specific 'request' attribute, with an alternative callback
        """
        crawler = get_crawler(
            AlternativeCallbacksSpider,
            {
                "DOWNLOADER_MIDDLEWARES": {
                    AlternativeCallbacksMiddleware: 595,
                }
            },
        )

        url = mockserver.url("/status?n=200")
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(seed=url, mockserver=mockserver)
        assert (
            "alternative_callbacks_spider",
            logging.INFO,
            "alt_callback was invoked with foo=bar",
        ) in caplog.record_tuples
