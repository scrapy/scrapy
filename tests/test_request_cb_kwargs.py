from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scrapy.http import Request
from scrapy.utils.test import get_crawler
from tests.spiders import MockServerSpider
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    import pytest

    from tests.mockserver.http import MockServer


class InjectArgumentsDownloaderMiddleware:
    """
    Make sure downloader middlewares are able to update the keyword arguments
    """

    def process_request(self, request):
        if request.callback.__name__ == "parse_downloader_mw":
            request.cb_kwargs["from_process_request"] = True

    def process_response(self, request, response):
        if request.callback.__name__ == "parse_downloader_mw":
            request.cb_kwargs["from_process_response"] = True
        return response


class InjectArgumentsSpiderMiddleware:
    """
    Make sure spider middlewares are able to update the keyword arguments
    """

    async def process_start(self, start):
        async for request in start:
            if request.callback.__name__ == "parse_spider_mw":
                request.cb_kwargs["from_process_start"] = True
            yield request

    def process_spider_input(self, response):
        request = response.request
        if request.callback.__name__ == "parse_spider_mw":
            request.cb_kwargs["from_process_spider_input"] = True

    async def process_spider_output(self, response, result):
        async for element in result:
            if (
                isinstance(element, Request)
                and element.callback
                and element.callback.__name__ == "parse_spider_mw_2"
            ):
                element.cb_kwargs["from_process_spider_output"] = True
            yield element


class KeywordArgumentsSpider(MockServerSpider):
    name = "kwargs"
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            InjectArgumentsDownloaderMiddleware: 750,
        },
        "SPIDER_MIDDLEWARES": {
            InjectArgumentsSpiderMiddleware: 750,
        },
    }

    checks: list[bool] = []

    def _inc_checks(self, count: int = 1) -> None:
        self.crawler.stats.inc_value("boolean_checks", count)

    async def start(self):
        assert self.mockserver
        data = {"key": "value", "number": 123, "callback": "some_callback"}
        yield Request(self.mockserver.url("/first"), self.parse_first, cb_kwargs=data)
        yield Request(
            self.mockserver.url("/general_with"), self.parse_general, cb_kwargs=data
        )
        yield Request(self.mockserver.url("/general_without"), self.parse_general)
        yield Request(self.mockserver.url("/no_kwargs"), self.parse_no_kwargs)
        yield Request(
            self.mockserver.url("/default"), self.parse_default, cb_kwargs=data
        )
        yield Request(
            self.mockserver.url("/takes_less"), self.parse_takes_less, cb_kwargs=data
        )
        yield Request(
            self.mockserver.url("/takes_more"), self.parse_takes_more, cb_kwargs=data
        )
        yield Request(self.mockserver.url("/downloader_mw"), self.parse_downloader_mw)
        yield Request(self.mockserver.url("/spider_mw"), self.parse_spider_mw)

    def parse_first(self, response, key, number):
        assert self.mockserver
        self.checks.append(key == "value")
        self.checks.append(number == 123)
        self._inc_checks(2)
        yield response.follow(
            self.mockserver.url("/two"),
            self.parse_second,
            cb_kwargs={"new_key": "new_value"},
        )

    def parse_second(self, response, new_key):
        self.checks.append(new_key == "new_value")
        self._inc_checks()

    def parse_general(self, response, **kwargs):
        if response.url.endswith("/general_with"):
            self.checks.append(kwargs["key"] == "value")
            self.checks.append(kwargs["number"] == 123)
            self.checks.append(kwargs["callback"] == "some_callback")
            self._inc_checks(3)
        elif response.url.endswith("/general_without"):
            self.checks.append(kwargs == {})
            self._inc_checks()

    def parse_no_kwargs(self, response):
        self.checks.append(response.url.endswith("/no_kwargs"))
        self._inc_checks()

    def parse_default(self, response, key, number=None, default=99):
        self.checks.append(response.url.endswith("/default"))
        self.checks.append(key == "value")
        self.checks.append(number == 123)
        self.checks.append(default == 99)
        self._inc_checks(4)

    def parse_takes_less(self, response, key, callback):
        """
        Should raise
        TypeError: parse_takes_less() got an unexpected keyword argument 'number'
        """

    def parse_takes_more(self, response, key, number, callback, other):
        """
        Should raise
        TypeError: parse_takes_more() missing 1 required positional argument: 'other'
        """

    def parse_downloader_mw(
        self, response, from_process_request, from_process_response
    ):
        self.checks.append(bool(from_process_request))
        self.checks.append(bool(from_process_response))
        self._inc_checks(2)

    def parse_spider_mw(self, response, from_process_spider_input, from_process_start):
        assert self.mockserver
        self.checks.append(bool(from_process_spider_input))
        self.checks.append(bool(from_process_start))
        self._inc_checks(2)
        return Request(self.mockserver.url("/spider_mw_2"), self.parse_spider_mw_2)

    def parse_spider_mw_2(self, response, from_process_spider_output):
        self.checks.append(bool(from_process_spider_output))
        self._inc_checks()


class TestCallbackKeywordArguments:
    @coroutine_test
    async def test_callback_kwargs(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(KeywordArgumentsSpider)
        with caplog.at_level(logging.ERROR):
            await crawler.crawl_async(mockserver=mockserver)
        assert isinstance(crawler.spider, KeywordArgumentsSpider)
        assert all(crawler.spider.checks)
        assert len(crawler.spider.checks) == crawler.stats.get_value("boolean_checks")
        # check exceptions for argument mismatch
        exceptions = {}
        for line in caplog.records:
            for key in ("takes_less", "takes_more"):
                if key in line.getMessage():
                    exceptions[key] = line
        takes_less_exc_info = exceptions["takes_less"].exc_info
        assert takes_less_exc_info is not None
        assert takes_less_exc_info[0] is TypeError
        assert str(takes_less_exc_info[1]).endswith(
            "parse_takes_less() got an unexpected keyword argument 'number'"
        )
        takes_more_exc_info = exceptions["takes_more"].exc_info
        assert takes_more_exc_info is not None
        assert takes_more_exc_info[0] is TypeError
        assert str(takes_more_exc_info[1]).endswith(
            "parse_takes_more() missing 1 required positional argument: 'other'"
        )
