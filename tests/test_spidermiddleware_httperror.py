import logging

import pytest
from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial.unittest import TestCase

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


def _responses(request, status_codes):
    responses = []
    for code in status_codes:
        response = Response(request.url, status=code)
        response.request = request
        responses.append(response)
    return responses


class TestHttpErrorMiddleware:
    def setup_method(self):
        crawler = get_crawler(Spider)
        self.spider = Spider.from_crawler(crawler, name="foo")
        self.mw = HttpErrorMiddleware(Settings({}))
        self.req = Request("http://scrapytest.org")
        self.res200, self.res404 = _responses(self.req, [200, 404])

    def test_process_spider_input(self):
        assert self.mw.process_spider_input(self.res200, self.spider) is None
        with pytest.raises(HttpError):
            self.mw.process_spider_input(self.res404, self.spider)

    def test_process_spider_exception(self):
        assert (
            self.mw.process_spider_exception(
                self.res404, HttpError(self.res404), self.spider
            )
            == []
        )
        assert (
            self.mw.process_spider_exception(self.res404, Exception(), self.spider)
            is None
        )

    def test_handle_httpstatus_list(self):
        res = self.res404.copy()
        res.request = Request(
            "http://scrapytest.org", meta={"handle_httpstatus_list": [404]}
        )
        assert self.mw.process_spider_input(res, self.spider) is None

        self.spider.handle_httpstatus_list = [404]
        assert self.mw.process_spider_input(self.res404, self.spider) is None


class TestHttpErrorMiddlewareSettings:
    """Similar test, but with settings"""

    def setup_method(self):
        self.spider = Spider("foo")
        self.mw = HttpErrorMiddleware(Settings({"HTTPERROR_ALLOWED_CODES": (402,)}))
        self.req = Request("http://scrapytest.org")
        self.res200, self.res404, self.res402 = _responses(self.req, [200, 404, 402])

    def test_process_spider_input(self):
        assert self.mw.process_spider_input(self.res200, self.spider) is None
        with pytest.raises(HttpError):
            self.mw.process_spider_input(self.res404, self.spider)
        assert self.mw.process_spider_input(self.res402, self.spider) is None

    def test_meta_overrides_settings(self):
        request = Request(
            "http://scrapytest.org", meta={"handle_httpstatus_list": [404]}
        )
        res404 = self.res404.copy()
        res404.request = request
        res402 = self.res402.copy()
        res402.request = request

        assert self.mw.process_spider_input(res404, self.spider) is None
        with pytest.raises(HttpError):
            self.mw.process_spider_input(res402, self.spider)

    def test_spider_override_settings(self):
        self.spider.handle_httpstatus_list = [404]
        assert self.mw.process_spider_input(self.res404, self.spider) is None
        with pytest.raises(HttpError):
            self.mw.process_spider_input(self.res402, self.spider)


class TestHttpErrorMiddlewareHandleAll:
    def setup_method(self):
        self.spider = Spider("foo")
        self.mw = HttpErrorMiddleware(Settings({"HTTPERROR_ALLOW_ALL": True}))
        self.req = Request("http://scrapytest.org")
        self.res200, self.res404, self.res402 = _responses(self.req, [200, 404, 402])

    def test_process_spider_input(self):
        assert self.mw.process_spider_input(self.res200, self.spider) is None
        assert self.mw.process_spider_input(self.res404, self.spider) is None

    def test_meta_overrides_settings(self):
        request = Request(
            "http://scrapytest.org", meta={"handle_httpstatus_list": [404]}
        )
        res404 = self.res404.copy()
        res404.request = request
        res402 = self.res402.copy()
        res402.request = request

        assert self.mw.process_spider_input(res404, self.spider) is None
        with pytest.raises(HttpError):
            self.mw.process_spider_input(res402, self.spider)

    def test_httperror_allow_all_false(self):
        crawler = get_crawler(_HttpErrorSpider)
        mw = HttpErrorMiddleware.from_crawler(crawler)
        request_httpstatus_false = Request(
            "http://scrapytest.org", meta={"handle_httpstatus_all": False}
        )
        request_httpstatus_true = Request(
            "http://scrapytest.org", meta={"handle_httpstatus_all": True}
        )
        res404 = self.res404.copy()
        res404.request = request_httpstatus_false
        res402 = self.res402.copy()
        res402.request = request_httpstatus_true

        with pytest.raises(HttpError):
            mw.process_spider_input(res404, self.spider)
        assert mw.process_spider_input(res402, self.spider) is None


class TestHttpErrorMiddlewareIntegrational(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
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

    @defer.inlineCallbacks
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

    @defer.inlineCallbacks
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
