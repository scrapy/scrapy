from __future__ import annotations

import logging

import pytest
from testfixtures import LogCapture
from twisted.internet.defer import inlineCallbacks

from scrapy.http import Request, Response
from scrapy.settings import Settings
from scrapy.spidermiddlewares.httperror import HttpError, HttpErrorMiddleware
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer
from tests.spiders import MockServerSpider


class _HttpErrorSpider(MockServerSpider):
    name = "httperror"
    bypass_status_codes: set[int] = set()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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

    def parse(self, response):
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
def spider() -> Spider:
    crawler = get_crawler(Spider)
    return Spider.from_crawler(crawler, name="foo")


@pytest.fixture
def res200() -> Response:
    return _response(req, 200)


@pytest.fixture
def res402() -> Response:
    return _response(req, 402)


@pytest.fixture
def res404() -> Response:
    return _response(req, 404)


class TestHttpErrorMiddleware:
    @pytest.fixture
    def mw(self) -> HttpErrorMiddleware:
        return HttpErrorMiddleware(Settings({}))

    def test_process_spider_input(
        self,
        mw: HttpErrorMiddleware,
        spider: Spider,
        res200: Response,
        res404: Response,
    ) -> None:
        mw.process_spider_input(res200, spider)
        with pytest.raises(HttpError):
            mw.process_spider_input(res404, spider)

    def test_process_spider_exception(
        self, mw: HttpErrorMiddleware, spider: Spider, res404: Response
    ) -> None:
        assert mw.process_spider_exception(res404, HttpError(res404), spider) == []
        assert mw.process_spider_exception(res404, Exception(), spider) is None

    def test_handle_httpstatus_list(
        self, mw: HttpErrorMiddleware, spider: Spider, res404: Response
    ) -> None:
        request = Request(
            "http://scrapytest.org", meta={"handle_httpstatus_list": [404]}
        )
        res = _response(request, 404)
        mw.process_spider_input(res, spider)

        spider.handle_httpstatus_list = [404]  # type: ignore[attr-defined]
        mw.process_spider_input(res404, spider)


class TestHttpErrorMiddlewareSettings:
    """Similar test, but with settings"""

    @pytest.fixture
    def mw(self) -> HttpErrorMiddleware:
        return HttpErrorMiddleware(Settings({"HTTPERROR_ALLOWED_CODES": (402,)}))

    def test_process_spider_input(
        self,
        mw: HttpErrorMiddleware,
        spider: Spider,
        res200: Response,
        res402: Response,
        res404: Response,
    ) -> None:
        mw.process_spider_input(res200, spider)
        with pytest.raises(HttpError):
            mw.process_spider_input(res404, spider)
        mw.process_spider_input(res402, spider)

    def test_meta_overrides_settings(
        self, mw: HttpErrorMiddleware, spider: Spider
    ) -> None:
        request = Request(
            "http://scrapytest.org", meta={"handle_httpstatus_list": [404]}
        )
        res404 = _response(request, 404)
        res402 = _response(request, 402)

        mw.process_spider_input(res404, spider)
        with pytest.raises(HttpError):
            mw.process_spider_input(res402, spider)

    def test_spider_override_settings(
        self,
        mw: HttpErrorMiddleware,
        spider: Spider,
        res402: Response,
        res404: Response,
    ) -> None:
        spider.handle_httpstatus_list = [404]  # type: ignore[attr-defined]
        mw.process_spider_input(res404, spider)
        with pytest.raises(HttpError):
            mw.process_spider_input(res402, spider)


class TestHttpErrorMiddlewareHandleAll:
    @pytest.fixture
    def mw(self) -> HttpErrorMiddleware:
        return HttpErrorMiddleware(Settings({"HTTPERROR_ALLOW_ALL": True}))

    def test_process_spider_input(
        self,
        mw: HttpErrorMiddleware,
        spider: Spider,
        res200: Response,
        res404: Response,
    ) -> None:
        mw.process_spider_input(res200, spider)
        mw.process_spider_input(res404, spider)

    def test_meta_overrides_settings(
        self, mw: HttpErrorMiddleware, spider: Spider
    ) -> None:
        request = Request(
            "http://scrapytest.org", meta={"handle_httpstatus_list": [404]}
        )
        res404 = _response(request, 404)
        res402 = _response(request, 402)

        mw.process_spider_input(res404, spider)
        with pytest.raises(HttpError):
            mw.process_spider_input(res402, spider)

    def test_httperror_allow_all_false(self, spider: Spider) -> None:
        crawler = get_crawler(_HttpErrorSpider)
        mw = HttpErrorMiddleware.from_crawler(crawler)
        request_httpstatus_false = Request(
            "http://scrapytest.org", meta={"handle_httpstatus_all": False}
        )
        request_httpstatus_true = Request(
            "http://scrapytest.org", meta={"handle_httpstatus_all": True}
        )
        res404 = _response(request_httpstatus_false, 404)
        res402 = _response(request_httpstatus_true, 402)

        with pytest.raises(HttpError):
            mw.process_spider_input(res404, spider)
        mw.process_spider_input(res402, spider)


class TestHttpErrorMiddlewareIntegrational:
    @classmethod
    def setup_class(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def teardown_class(cls):
        cls.mockserver.__exit__(None, None, None)

    @inlineCallbacks
    def test_middleware_works(self):
        crawler = get_crawler(_HttpErrorSpider)
        yield crawler.crawl(mockserver=self.mockserver)
        assert not crawler.spider.skipped, crawler.spider.skipped
        assert crawler.spider.parsed == {"200"}
        assert crawler.spider.failed == {"404", "402", "500"}

        get_value = crawler.stats.get_value
        assert get_value("httperror/response_ignored_count") == 3
        assert get_value("httperror/response_ignored_status_count/404") == 1
        assert get_value("httperror/response_ignored_status_count/402") == 1
        assert get_value("httperror/response_ignored_status_count/500") == 1

    @inlineCallbacks
    def test_logging(self):
        crawler = get_crawler(_HttpErrorSpider)
        with LogCapture() as log:
            yield crawler.crawl(mockserver=self.mockserver, bypass_status_codes={402})
        assert crawler.spider.parsed == {"200", "402"}
        assert crawler.spider.skipped == {"402"}
        assert crawler.spider.failed == {"404", "500"}

        assert "Ignoring response <404" in str(log)
        assert "Ignoring response <500" in str(log)
        assert "Ignoring response <200" not in str(log)
        assert "Ignoring response <402" not in str(log)

    @inlineCallbacks
    def test_logging_level(self):
        # HttpError logs ignored responses with level INFO
        crawler = get_crawler(_HttpErrorSpider)
        with LogCapture(level=logging.INFO) as log:
            yield crawler.crawl(mockserver=self.mockserver)
        assert crawler.spider.parsed == {"200"}
        assert crawler.spider.failed == {"404", "402", "500"}

        assert "Ignoring response <402" in str(log)
        assert "Ignoring response <404" in str(log)
        assert "Ignoring response <500" in str(log)
        assert "Ignoring response <200" not in str(log)

        # with level WARNING, we shouldn't capture anything from HttpError
        crawler = get_crawler(_HttpErrorSpider)
        with LogCapture(level=logging.WARNING) as log:
            yield crawler.crawl(mockserver=self.mockserver)
        assert crawler.spider.parsed == {"200"}
        assert crawler.spider.failed == {"404", "402", "500"}

        assert "Ignoring response <402" not in str(log)
        assert "Ignoring response <404" not in str(log)
        assert "Ignoring response <500" not in str(log)
        assert "Ignoring response <200" not in str(log)
