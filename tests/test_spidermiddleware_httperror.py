from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, Any

import pytest

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.spidermiddlewares.httperror import HttpError, HttpErrorMiddleware
from scrapy.utils.datatypes import SequenceExclude
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.spiders import MockServerSpider
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy import Spider
    from tests.mockserver.http import MockServer


class _HttpErrorSpider(MockServerSpider):
    name = "httperror"
    bypass_status_codes: set[int] = set()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert self.mockserver
        self.start_urls = [
            self.mockserver.url("/status?n=200"),
            self.mockserver.url("/status?n=404"),
            self.mockserver.url("/status?n=402"),
            self.mockserver.url("/status?n=500"),
        ]
        self.failed = set()
        self.skipped = set()
        self.parsed = set()

    async def start(self):
        for url in self.start_urls:
            yield Request(url, self.parse, errback=self.on_error)

    def parse(self, response: Response) -> None:
        self.parsed.add(response.url[-3:])

    def on_error(self, failure):
        if isinstance(failure.value, HttpError):
            response = failure.value.response
            if response.status in self.bypass_status_codes:
                self.skipped.add(response.url[-3:])
                return self.parse(response)

        # it assumes there is a response attached to failure
        self.failed.add(failure.value.response.url[-3:])
        return failure


req = Request("http://scrapytest.org")


def _response(request: Request, status_code: int) -> Response:
    return Response(request.url, status=status_code, request=request)


@pytest.fixture
def res200() -> Response:
    return _response(req, 200)


@pytest.fixture
def res402() -> Response:
    return _response(req, 402)


@pytest.fixture
def res404() -> Response:
    return _response(req, 404)


def _mw(
    settings: dict[str, Any] | None = None, spidercls: type[Spider] = DefaultSpider
) -> HttpErrorMiddleware:
    crawler = get_crawler(spidercls, settings)
    crawler.spider = crawler._create_spider()
    mw = build_from_crawler(HttpErrorMiddleware, crawler)
    mw.spider_opened(crawler.spider)
    return mw


class TestHttpErrorMiddleware:
    @pytest.fixture
    def mw(self) -> HttpErrorMiddleware:
        return _mw()

    def test_process_spider_input(
        self, mw: HttpErrorMiddleware, res200: Response, res404: Response
    ) -> None:
        mw.process_spider_input(res200)
        with pytest.raises(HttpError):
            mw.process_spider_input(res404)

    def test_process_spider_exception(
        self, mw: HttpErrorMiddleware, res404: Response
    ) -> None:
        assert mw.process_spider_exception(res404, HttpError(res404)) == ()
        assert mw.process_spider_exception(res404, Exception()) is None

    def test_meta(self, mw: HttpErrorMiddleware, res404: Response) -> None:
        request = Request("http://example.com", meta={"handle_http_codes": [404]})
        mw.process_spider_input(_response(request, 404))
        with pytest.raises(HttpError):
            mw.process_spider_input(_response(request, 402))
        with pytest.raises(HttpError):
            mw.process_spider_input(res404)


class TestHttpErrorMiddlewareSettings:
    """Similar test, but with settings"""

    @pytest.fixture
    def mw(self) -> HttpErrorMiddleware:
        return _mw({"HANDLE_HTTP_CODES": (402,)})

    def test_process_spider_input(
        self,
        mw: HttpErrorMiddleware,
        res200: Response,
        res402: Response,
        res404: Response,
    ) -> None:
        mw.process_spider_input(res200)
        with pytest.raises(HttpError):
            mw.process_spider_input(res404)
        mw.process_spider_input(res402)

    def test_meta_overrides_settings(self, mw: HttpErrorMiddleware) -> None:
        request = Request("http://example.com", meta={"handle_http_codes": [404]})
        mw.process_spider_input(_response(request, 404))
        with pytest.raises(HttpError):
            mw.process_spider_input(_response(request, 402))

    def test_meta_false_overrides_settings(self, mw: HttpErrorMiddleware) -> None:
        request = Request("http://example.com", meta={"handle_http_codes": False})
        with pytest.raises(HttpError):
            mw.process_spider_input(_response(request, 402))

    def test_meta_none_ignored(self, mw: HttpErrorMiddleware) -> None:
        request = Request("http://example.com", meta={"handle_http_codes": None})
        mw.process_spider_input(_response(request, 402))


class TestHttpErrorMiddlewareHandleAll:
    @pytest.fixture
    def mw(self) -> HttpErrorMiddleware:
        return _mw({"HANDLE_HTTP_CODES": True})

    def test_process_spider_input(
        self,
        mw: HttpErrorMiddleware,
        res200: Response,
        res404: Response,
    ) -> None:
        mw.process_spider_input(res200)
        mw.process_spider_input(res404)

    def test_meta_overrides_settings(self, mw: HttpErrorMiddleware) -> None:
        request = Request("http://example.com", meta={"handle_http_codes": [404]})
        mw.process_spider_input(_response(request, 404))
        with pytest.raises(HttpError):
            mw.process_spider_input(_response(request, 402))

    def test_meta_false_overrides_settings(self, mw: HttpErrorMiddleware) -> None:
        request = Request("http://example.com", meta={"handle_http_codes": False})
        with pytest.raises(HttpError):
            mw.process_spider_input(_response(request, 402))


class TestHttpErrorMiddlewareValues:
    """Every supported way to express a HANDLE_HTTP_CODES value."""

    @pytest.mark.parametrize(
        ("value", "handled"),
        [
            (True, True),
            (False, False),
            (None, False),
            (402, True),
            ("402", True),
            ("402,404", True),
            ("True", True),
            ("true", True),
            ("1", True),
            ("False", False),
            ("false", False),
            ("0", False),
            ("", False),
            ([402], True),
            (["402"], True),
            ((402,), True),
            ({402}, True),
            (frozenset({402}), True),
            ([], False),
            ([404], False),
            (SequenceExclude(range(300, 400)), True),
        ],
    )
    def test_setting(self, value: Any, handled: bool) -> None:
        mw = _mw({"HANDLE_HTTP_CODES": value})
        res402 = _response(Request("http://example.com"), 402)
        if handled:
            mw.process_spider_input(res402)
        else:
            with pytest.raises(HttpError):
                mw.process_spider_input(res402)

    @pytest.mark.parametrize(
        ("value", "handled"),
        [
            (True, True),
            (False, False),
            (402, True),
            ("402", True),
            ([402], True),
            ([404], False),
            (SequenceExclude(range(300, 400)), True),
        ],
    )
    def test_meta(self, value: Any, handled: bool) -> None:
        mw = _mw()
        request = Request("http://example.com", meta={"handle_http_codes": value})
        if handled:
            mw.process_spider_input(_response(request, 402))
        else:
            with pytest.raises(HttpError):
                mw.process_spider_input(_response(request, 402))

    def test_unsupported_value(self) -> None:
        with pytest.raises(ValueError, match="Unsupported HANDLE_HTTP_CODES value"):
            _mw({"HANDLE_HTTP_CODES": object()})


class TestHttpErrorMiddlewareDeprecated:
    def test_settings(self) -> None:
        with pytest.warns(
            ScrapyDeprecationWarning, match="HTTPERROR_ALLOWED_CODES setting"
        ):
            mw = _mw({"HTTPERROR_ALLOWED_CODES": (402,)})
        res402 = _response(Request("http://example.com"), 402)
        res404 = _response(Request("http://example.com"), 404)
        mw.process_spider_input(res402)
        with pytest.raises(HttpError):
            mw.process_spider_input(res404)

    def test_allow_all_setting(self) -> None:
        with pytest.warns(
            ScrapyDeprecationWarning, match="HTTPERROR_ALLOW_ALL setting"
        ):
            mw = _mw({"HTTPERROR_ALLOW_ALL": True})
        mw.process_spider_input(_response(Request("http://example.com"), 404))

    def test_new_setting_wins(self) -> None:
        mw = _mw({"HANDLE_HTTP_CODES": False, "HTTPERROR_ALLOW_ALL": True})
        with pytest.raises(HttpError):
            mw.process_spider_input(_response(Request("http://example.com"), 404))

    def test_spider_attribute(self) -> None:
        class HandlingSpider(DefaultSpider):
            handle_httpstatus_list = [404]

        with pytest.warns(
            ScrapyDeprecationWarning, match="'handle_httpstatus_list' spider attribute"
        ):
            mw = _mw(spidercls=HandlingSpider)
        mw.process_spider_input(_response(Request("http://example.com"), 404))
        with pytest.raises(HttpError):
            mw.process_spider_input(_response(Request("http://example.com"), 402))

    def test_spider_attribute_overrides_settings(self) -> None:
        class HandlingSpider(DefaultSpider):
            handle_httpstatus_list = [404]

        with pytest.warns(ScrapyDeprecationWarning):
            mw = _mw({"HANDLE_HTTP_CODES": [402]}, spidercls=HandlingSpider)
        mw.process_spider_input(_response(Request("http://example.com"), 404))
        with pytest.raises(HttpError):
            mw.process_spider_input(_response(Request("http://example.com"), 402))

    def test_meta_overrides_spider_attribute(self) -> None:
        """Unlike RedirectMiddleware, this middleware never combined the
        deprecated meta key with the deprecated spider attribute."""

        class HandlingSpider(DefaultSpider):
            handle_httpstatus_list = [404]

        with pytest.warns(ScrapyDeprecationWarning):
            mw = _mw(spidercls=HandlingSpider)
        request = Request("http://example.com", meta={"handle_httpstatus_list": [402]})
        with pytest.warns(ScrapyDeprecationWarning), pytest.raises(HttpError):
            mw.process_spider_input(_response(request, 404))

    def test_meta_list(self) -> None:
        mw = _mw()
        request = Request("http://example.com", meta={"handle_httpstatus_list": [404]})
        with pytest.warns(
            ScrapyDeprecationWarning, match="'handle_httpstatus_list' request meta key"
        ):
            mw.process_spider_input(_response(request, 404))
        with pytest.raises(HttpError):
            mw.process_spider_input(_response(request, 402))

    def test_meta_all(self) -> None:
        mw = _mw()
        request = Request("http://example.com", meta={"handle_httpstatus_all": True})
        with pytest.warns(
            ScrapyDeprecationWarning, match="'handle_httpstatus_all' request meta key"
        ):
            mw.process_spider_input(_response(request, 404))

    def test_meta_all_false(self) -> None:
        mw = _mw({"HANDLE_HTTP_CODES": True})
        request = Request("http://example.com", meta={"handle_httpstatus_all": False})
        with pytest.warns(ScrapyDeprecationWarning), pytest.raises(HttpError):
            mw.process_spider_input(_response(request, 404))

    def test_meta_all_true_beats_meta_list(self) -> None:
        mw = _mw()
        request = Request(
            "http://example.com",
            meta={"handle_httpstatus_all": True, "handle_httpstatus_list": [404]},
        )
        with pytest.warns(ScrapyDeprecationWarning):
            mw.process_spider_input(_response(request, 402))

    def test_meta_all_false_defers_to_meta_list(self) -> None:
        mw = _mw()
        request = Request(
            "http://example.com",
            meta={"handle_httpstatus_all": False, "handle_httpstatus_list": [404]},
        )
        with pytest.warns(ScrapyDeprecationWarning):
            mw.process_spider_input(_response(request, 404))

    def test_new_meta_key_wins(self) -> None:
        mw = _mw()
        request = Request(
            "http://example.com",
            meta={"handle_http_codes": False, "handle_httpstatus_all": True},
        )
        with pytest.raises(HttpError):
            mw.process_spider_input(_response(request, 404))

    def test_meta_key_warning_once_per_crawl(self) -> None:
        mw = _mw()
        request = Request("http://example.com", meta={"handle_httpstatus_all": True})
        with pytest.warns(ScrapyDeprecationWarning):
            mw.process_spider_input(_response(request, 404))
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            mw.process_spider_input(_response(request, 404))


class TestHttpErrorMiddlewareIntegrational:
    @coroutine_test
    async def test_middleware_works(self, mockserver: MockServer) -> None:
        crawler = get_crawler(_HttpErrorSpider)
        await crawler.crawl_async(mockserver=mockserver)
        assert isinstance(crawler.spider, _HttpErrorSpider)
        assert not crawler.spider.skipped
        assert crawler.spider.parsed == {"200"}
        assert crawler.spider.failed == {"404", "402", "500"}

        get_value = crawler.stats.get_value
        assert get_value("httperror/response_ignored_count") == 3
        assert get_value("httperror/response_ignored_status_count/404") == 1
        assert get_value("httperror/response_ignored_status_count/402") == 1
        assert get_value("httperror/response_ignored_status_count/500") == 1

    @coroutine_test
    async def test_setting(self, mockserver: MockServer) -> None:
        crawler = get_crawler(_HttpErrorSpider, {"HANDLE_HTTP_CODES": [402, 404]})
        await crawler.crawl_async(mockserver=mockserver)
        assert isinstance(crawler.spider, _HttpErrorSpider)
        assert crawler.spider.parsed == {"200", "402", "404"}
        assert crawler.spider.failed == {"500"}

    @coroutine_test
    async def test_setting_all(self, mockserver: MockServer) -> None:
        crawler = get_crawler(_HttpErrorSpider, {"HANDLE_HTTP_CODES": True})
        await crawler.crawl_async(mockserver=mockserver)
        assert isinstance(crawler.spider, _HttpErrorSpider)
        assert crawler.spider.parsed == {"200", "402", "404", "500"}
        assert not crawler.spider.failed

    @coroutine_test
    async def test_logging(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        crawler = get_crawler(_HttpErrorSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(mockserver=mockserver, bypass_status_codes={402})
        assert isinstance(crawler.spider, _HttpErrorSpider)
        assert crawler.spider.parsed == {"200", "402"}
        assert crawler.spider.skipped == {"402"}
        assert crawler.spider.failed == {"404", "500"}

        assert "Ignoring response <404" in caplog.text
        assert "Ignoring response <500" in caplog.text
        assert "Ignoring response <200" not in caplog.text
        assert "Ignoring response <402" not in caplog.text

    @coroutine_test
    async def test_logging_level(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        # HttpError logs ignored responses with level INFO
        crawler = get_crawler(_HttpErrorSpider)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async(mockserver=mockserver)
        assert isinstance(crawler.spider, _HttpErrorSpider)
        assert crawler.spider.parsed == {"200"}
        assert crawler.spider.failed == {"404", "402", "500"}

        assert "Ignoring response <402" in caplog.text
        assert "Ignoring response <404" in caplog.text
        assert "Ignoring response <500" in caplog.text
        assert "Ignoring response <200" not in caplog.text

        # with level WARNING, we shouldn't capture anything from HttpError
        caplog.clear()
        crawler = get_crawler(_HttpErrorSpider)
        with caplog.at_level(logging.WARNING):
            await crawler.crawl_async(mockserver=mockserver)
        assert isinstance(crawler.spider, _HttpErrorSpider)
        assert crawler.spider.parsed == {"200"}
        assert crawler.spider.failed == {"404", "402", "500"}

        assert "Ignoring response <402" not in caplog.text
        assert "Ignoring response <404" not in caplog.text
        assert "Ignoring response <500" not in caplog.text
        assert "Ignoring response <200" not in caplog.text
