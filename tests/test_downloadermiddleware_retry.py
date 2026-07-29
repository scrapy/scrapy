from __future__ import annotations

import logging
from typing import Any, cast

import pytest
from twisted.internet.error import ConnectError, ConnectionDone, ConnectionLost

from scrapy.downloadermiddlewares.retry import RetryMiddleware, get_retry_request
from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadConnectionRefusedError,
    DownloadTimeoutError,
    IgnoreRequest,
)
from scrapy.http import Request, Response
from scrapy.settings.default_settings import RETRY_EXCEPTIONS
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler


class TestRetry:
    def setup_method(self):
        self.crawler = get_crawler(DefaultSpider)
        self.crawler.spider = self.crawler._create_spider()
        self.mw = build_from_crawler(RetryMiddleware, self.crawler)
        self.mw.max_retry_times = 2

    def test_priority_adjust(self):
        req = Request("http://www.scrapytest.org/503")
        rsp = Response("http://www.scrapytest.org/503", body=b"", status=503)
        req2 = self.mw.process_response(req, rsp)
        assert req2.priority < req.priority

    def test_404(self):
        req = Request("http://www.scrapytest.org/404")
        rsp = Response("http://www.scrapytest.org/404", body=b"", status=404)

        # dont retry 404s
        assert self.mw.process_response(req, rsp) is rsp

    def test_dont_retry(self):
        req = Request("http://www.scrapytest.org/503", meta={"dont_retry": True})
        rsp = Response("http://www.scrapytest.org/503", body=b"", status=503)

        # no retry
        r = self.mw.process_response(req, rsp)
        assert r is rsp

        # Test retry when dont_retry set to False
        req = Request("http://www.scrapytest.org/503", meta={"dont_retry": False})
        rsp = Response("http://www.scrapytest.org/503", body=b"", status=503)

        # first retry
        req = self.mw.process_response(req, rsp)
        assert isinstance(req, Request)
        assert req.meta["retry_times"] == 1

    def test_dont_retry_exc(self):
        req = Request("http://www.scrapytest.org/503", meta={"dont_retry": True})

        r = self.mw.process_exception(req, CannotResolveHostError())
        assert r is None

    def test_503(self):
        req = Request("http://www.scrapytest.org/503")
        rsp = Response("http://www.scrapytest.org/503", body=b"", status=503)

        # first retry
        req = self.mw.process_response(req, rsp)
        assert isinstance(req, Request)
        assert req.meta["retry_times"] == 1

        # second retry
        req = self.mw.process_response(req, rsp)
        assert isinstance(req, Request)
        assert req.meta["retry_times"] == 2

        # discard it
        assert self.mw.process_response(req, rsp) is rsp

        assert self.crawler.stats.get_value("retry/max_reached") == 1
        assert (
            self.crawler.stats.get_value("retry/reason_count/503 Service Unavailable")
            == 2
        )
        assert self.crawler.stats.get_value("retry/count") == 2

    def test_give_up_log_level_setting(self, caplog: pytest.LogCaptureFixture) -> None:
        crawler = get_crawler(
            DefaultSpider, settings_dict={"RETRY_GIVE_UP_LOG_LEVEL": "WARNING"}
        )
        crawler.spider = crawler._create_spider()
        mw = build_from_crawler(RetryMiddleware, crawler)
        mw.max_retry_times = 0
        req = Request("http://example.com/503")
        rsp = Response("http://example.com/503", body=b"", status=503)
        with caplog.at_level(logging.WARNING):
            assert mw.process_response(req, rsp) is rsp
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.WARNING,
            f"Gave up retrying {req} (failed 1 times): 503 Service Unavailable",
        ) in caplog.record_tuples

    def test_give_up_log_level_meta(self, caplog: pytest.LogCaptureFixture) -> None:
        self.mw.max_retry_times = 0
        req = Request("http://example.com/503", meta={"give_up_log_level": "WARNING"})
        rsp = Response("http://example.com/503", body=b"", status=503)
        with caplog.at_level(logging.WARNING):
            assert self.mw.process_response(req, rsp) is rsp
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.WARNING,
            f"Gave up retrying {req} (failed 1 times): 503 Service Unavailable",
        ) in caplog.record_tuples

    def test_twistederrors(self):
        exceptions = [
            ConnectError,
            ConnectionDone,
            ConnectionLost,
            DownloadTimeoutError,
            DownloadConnectionRefusedError,
            CannotResolveHostError,
        ]

        for exc in exceptions:
            req = Request(f"http://www.scrapytest.org/{exc.__name__}")
            self._test_retry_exception(req, exc("foo"))

        stats = self.crawler.stats
        assert stats.get_value("retry/max_reached") == len(exceptions)
        assert stats.get_value("retry/count") == len(exceptions) * 2
        assert (
            stats.get_value("retry/reason_count/scrapy.exceptions.DownloadTimeoutError")
            == 2
        )

    def test_exception_to_retry_added(self):
        exc = ValueError
        settings_dict = {
            "RETRY_EXCEPTIONS": [*RETRY_EXCEPTIONS, exc],
        }
        crawler = get_crawler(DefaultSpider, settings_dict=settings_dict)
        crawler.spider = crawler._create_spider()
        mw = build_from_crawler(RetryMiddleware, crawler)
        req = Request(f"http://www.scrapytest.org/{exc.__name__}")
        self._test_retry_exception(req, exc("foo"), mw)

    def _test_retry_exception(self, req, exception, mw=None):
        if mw is None:
            mw = self.mw

        # first retry
        req = mw.process_exception(req, exception)
        assert isinstance(req, Request)
        assert req.meta["retry_times"] == 1

        # second retry
        req = mw.process_exception(req, exception)
        assert isinstance(req, Request)
        assert req.meta["retry_times"] == 2

        # discard it
        req = mw.process_exception(req, exception)
        assert req is None


class TestMaxRetryTimes:
    invalid_url = "http://www.scrapytest.org/invalid_url"

    def get_middleware(self, settings=None):
        crawler = get_crawler(DefaultSpider, settings or {})
        crawler.spider = crawler._create_spider()
        return build_from_crawler(RetryMiddleware, crawler)

    def test_with_settings_zero(self):
        max_retry_times = 0
        settings = {"RETRY_TIMES": max_retry_times}
        middleware = self.get_middleware(settings)
        req = Request(self.invalid_url)
        self._test_retry(
            req,
            CannotResolveHostError("foo"),
            max_retry_times,
            middleware=middleware,
        )

    def test_with_metakey_zero(self):
        max_retry_times = 0
        middleware = self.get_middleware()
        meta = {"max_retry_times": max_retry_times}
        req = Request(self.invalid_url, meta=meta)
        self._test_retry(
            req,
            CannotResolveHostError("foo"),
            max_retry_times,
            middleware=middleware,
        )

    def test_without_metakey(self):
        max_retry_times = 5
        settings = {"RETRY_TIMES": max_retry_times}
        middleware = self.get_middleware(settings)
        req = Request(self.invalid_url)
        self._test_retry(
            req,
            CannotResolveHostError("foo"),
            max_retry_times,
            middleware=middleware,
        )

    def test_with_metakey_greater(self):
        meta_max_retry_times = 3
        middleware_max_retry_times = 2

        req1 = Request(self.invalid_url, meta={"max_retry_times": meta_max_retry_times})
        req2 = Request(self.invalid_url)

        settings = {"RETRY_TIMES": middleware_max_retry_times}
        middleware = self.get_middleware(settings)

        self._test_retry(
            req1,
            CannotResolveHostError("foo"),
            meta_max_retry_times,
            middleware=middleware,
        )
        self._test_retry(
            req2,
            CannotResolveHostError("foo"),
            middleware_max_retry_times,
            middleware=middleware,
        )

    def test_with_metakey_lesser(self):
        meta_max_retry_times = 4
        middleware_max_retry_times = 5

        req1 = Request(self.invalid_url, meta={"max_retry_times": meta_max_retry_times})
        req2 = Request(self.invalid_url)

        settings = {"RETRY_TIMES": middleware_max_retry_times}
        middleware = self.get_middleware(settings)

        self._test_retry(
            req1,
            CannotResolveHostError("foo"),
            meta_max_retry_times,
            middleware=middleware,
        )
        self._test_retry(
            req2,
            CannotResolveHostError("foo"),
            middleware_max_retry_times,
            middleware=middleware,
        )

    def test_with_dont_retry(self):
        max_retry_times = 4
        middleware = self.get_middleware()
        meta = {
            "max_retry_times": max_retry_times,
            "dont_retry": True,
        }
        req = Request(self.invalid_url, meta=meta)
        self._test_retry(
            req,
            CannotResolveHostError("foo"),
            0,
            middleware=middleware,
        )

    def _test_retry(
        self,
        req,
        exception,
        max_retry_times,
        middleware=None,
    ):
        middleware = middleware or self.mw

        for _ in range(max_retry_times):
            req = middleware.process_exception(req, exception)
            assert isinstance(req, Request)

        # discard it
        req = middleware.process_exception(req, exception)
        assert req is None


class TestGetRetryRequest:
    @staticmethod
    def get_spider(settings: dict[str, Any] | None = None) -> Spider:
        crawler = get_crawler(Spider, settings or {})
        return crawler._create_spider("foo")

    def test_basic_usage(self, caplog: pytest.LogCaptureFixture) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        with caplog.at_level(logging.DEBUG):
            new_request = get_retry_request(
                request,
                spider=spider,
            )
        assert isinstance(new_request, Request)
        assert new_request != request
        assert new_request.dont_filter
        expected_retry_times = 1
        assert new_request.meta["retry_times"] == expected_retry_times
        assert new_request.priority == -1
        expected_reason = "unspecified"
        assert spider.crawler.stats
        for stat in ("retry/count", f"retry/reason_count/{expected_reason}"):
            assert spider.crawler.stats.get_value(stat) == 1
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.DEBUG,
            f"Retrying {request} (failed {expected_retry_times} times): "
            f"{expected_reason}",
        ) in caplog.record_tuples

    def test_max_retries_reached(self, caplog: pytest.LogCaptureFixture) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        max_retry_times = 0
        with caplog.at_level(logging.DEBUG):
            new_request = get_retry_request(
                request,
                spider=spider,
                max_retry_times=max_retry_times,
            )
        assert new_request is None
        assert spider.crawler.stats
        assert spider.crawler.stats.get_value("retry/max_reached") == 1
        failure_count = max_retry_times + 1
        expected_reason = "unspecified"
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.ERROR,
            f"Gave up retrying {request} (failed {failure_count} times): "
            f"{expected_reason}",
        ) in caplog.record_tuples

    def test_one_retry(self, caplog: pytest.LogCaptureFixture) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        with caplog.at_level(logging.DEBUG):
            new_request = get_retry_request(
                request,
                spider=spider,
                max_retry_times=1,
            )
        assert isinstance(new_request, Request)
        assert new_request != request
        assert new_request.dont_filter
        expected_retry_times = 1
        assert new_request.meta["retry_times"] == expected_retry_times
        assert new_request.priority == -1
        expected_reason = "unspecified"
        assert spider.crawler.stats
        for stat in ("retry/count", f"retry/reason_count/{expected_reason}"):
            assert spider.crawler.stats.get_value(stat) == 1
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.DEBUG,
            f"Retrying {request} (failed {expected_retry_times} times): "
            f"{expected_reason}",
        ) in caplog.record_tuples

    def test_two_retries(self, caplog: pytest.LogCaptureFixture) -> None:
        spider = self.get_spider()
        request = Request("https://example.com")
        new_request = request
        max_retry_times = 2
        for index in range(max_retry_times):
            caplog.clear()
            with caplog.at_level(logging.DEBUG):
                new_request = cast(
                    "Request",
                    get_retry_request(
                        new_request,
                        spider=spider,
                        max_retry_times=max_retry_times,
                    ),
                )
            assert isinstance(new_request, Request)
            assert new_request != request
            assert new_request.dont_filter
            expected_retry_times = index + 1
            assert new_request.meta["retry_times"] == expected_retry_times
            assert new_request.priority == -expected_retry_times
            expected_reason = "unspecified"
            assert spider.crawler.stats
            for stat in ("retry/count", f"retry/reason_count/{expected_reason}"):
                value = spider.crawler.stats.get_value(stat)
                assert value == expected_retry_times
            assert (
                "scrapy.downloadermiddlewares.retry",
                logging.DEBUG,
                f"Retrying {request} (failed {expected_retry_times} times): "
                f"{expected_reason}",
            ) in caplog.record_tuples

        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            new_request = cast(
                "Request",
                get_retry_request(
                    new_request,
                    spider=spider,
                    max_retry_times=max_retry_times,
                ),
            )
        assert new_request is None
        assert spider.crawler.stats.get_value("retry/max_reached") == 1
        failure_count = max_retry_times + 1
        expected_reason = "unspecified"
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.ERROR,
            f"Gave up retrying {request} (failed {failure_count} times): "
            f"{expected_reason}",
        ) in caplog.record_tuples

    def test_no_spider(self):
        request = Request("https://example.com")
        with pytest.raises(TypeError):
            get_retry_request(request)  # pylint: disable=missing-kwoa

    def test_max_retry_times_setting(self):
        max_retry_times = 0
        spider = self.get_spider({"RETRY_TIMES": max_retry_times})
        request = Request("https://example.com")
        new_request = get_retry_request(
            request,
            spider=spider,
        )
        assert new_request is None

    def test_max_retry_times_meta(self):
        max_retry_times = 0
        spider = self.get_spider({"RETRY_TIMES": max_retry_times + 1})
        meta = {"max_retry_times": max_retry_times}
        request = Request("https://example.com", meta=meta)
        new_request = get_retry_request(
            request,
            spider=spider,
        )
        assert new_request is None

    def test_max_retry_times_argument(self):
        max_retry_times = 0
        spider = self.get_spider({"RETRY_TIMES": max_retry_times + 1})
        meta = {"max_retry_times": max_retry_times + 1}
        request = Request("https://example.com", meta=meta)
        new_request = get_retry_request(
            request,
            spider=spider,
            max_retry_times=max_retry_times,
        )
        assert new_request is None

    def test_priority_adjust_setting(self):
        priority_adjust = 1
        spider = self.get_spider({"RETRY_PRIORITY_ADJUST": priority_adjust})
        request = Request("https://example.com")
        new_request = get_retry_request(
            request,
            spider=spider,
        )
        assert new_request.priority == priority_adjust

    def test_priority_adjust_argument(self):
        priority_adjust = 1
        spider = self.get_spider({"RETRY_PRIORITY_ADJUST": priority_adjust + 1})
        request = Request("https://example.com")
        new_request = get_retry_request(
            request,
            spider=spider,
            priority_adjust=priority_adjust,
        )
        assert new_request.priority == priority_adjust

    def test_log_extra_retry_success(self, caplog: pytest.LogCaptureFixture) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        with caplog.at_level(logging.DEBUG):
            get_retry_request(
                request,
                spider=spider,
            )
        assert any(getattr(r, "spider", None) is spider for r in caplog.records)

    def test_log_extra_retries_exceeded(self, caplog: pytest.LogCaptureFixture) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        with caplog.at_level(logging.DEBUG):
            get_retry_request(
                request,
                spider=spider,
                max_retry_times=0,
            )
        assert any(getattr(r, "spider", None) is spider for r in caplog.records)

    def test_reason_string(self, caplog: pytest.LogCaptureFixture) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        expected_reason = "because"
        with caplog.at_level(logging.DEBUG):
            get_retry_request(
                request,
                spider=spider,
                reason=expected_reason,
            )
        expected_retry_times = 1
        assert spider.crawler.stats
        for stat in ("retry/count", f"retry/reason_count/{expected_reason}"):
            assert spider.crawler.stats.get_value(stat) == 1
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.DEBUG,
            f"Retrying {request} (failed {expected_retry_times} times): "
            f"{expected_reason}",
        ) in caplog.record_tuples

    def test_reason_builtin_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        expected_reason = NotImplementedError()
        expected_reason_string = "builtins.NotImplementedError"
        with caplog.at_level(logging.DEBUG):
            get_retry_request(
                request,
                spider=spider,
                reason=expected_reason,
            )
        expected_retry_times = 1
        assert spider.crawler.stats
        stat = spider.crawler.stats.get_value(
            f"retry/reason_count/{expected_reason_string}"
        )
        assert stat == 1
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.DEBUG,
            f"Retrying {request} (failed {expected_retry_times} times): "
            f"{expected_reason}",
        ) in caplog.record_tuples

    def test_reason_builtin_exception_class(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        expected_reason = NotImplementedError
        expected_reason_string = "builtins.NotImplementedError"
        with caplog.at_level(logging.DEBUG):
            get_retry_request(
                request,
                spider=spider,
                reason=expected_reason,
            )
        expected_retry_times = 1
        assert spider.crawler.stats
        stat = spider.crawler.stats.get_value(
            f"retry/reason_count/{expected_reason_string}"
        )
        assert stat == 1
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.DEBUG,
            f"Retrying {request} (failed {expected_retry_times} times): "
            f"{expected_reason}",
        ) in caplog.record_tuples

    def test_reason_custom_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        expected_reason = IgnoreRequest()
        expected_reason_string = "scrapy.exceptions.IgnoreRequest"
        with caplog.at_level(logging.DEBUG):
            get_retry_request(
                request,
                spider=spider,
                reason=expected_reason,
            )
        expected_retry_times = 1
        assert spider.crawler.stats
        stat = spider.crawler.stats.get_value(
            f"retry/reason_count/{expected_reason_string}"
        )
        assert stat == 1
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.DEBUG,
            f"Retrying {request} (failed {expected_retry_times} times): "
            f"{expected_reason}",
        ) in caplog.record_tuples

    def test_reason_custom_exception_class(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        expected_reason = IgnoreRequest
        expected_reason_string = "scrapy.exceptions.IgnoreRequest"
        with caplog.at_level(logging.DEBUG):
            get_retry_request(
                request,
                spider=spider,
                reason=expected_reason,
            )
        expected_retry_times = 1
        assert spider.crawler.stats
        stat = spider.crawler.stats.get_value(
            f"retry/reason_count/{expected_reason_string}"
        )
        assert stat == 1
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.DEBUG,
            f"Retrying {request} (failed {expected_retry_times} times): "
            f"{expected_reason}",
        ) in caplog.record_tuples

    def test_custom_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = logging.getLogger("custom-logger")
        request = Request("https://example.com")
        spider = self.get_spider()
        expected_reason = "because"
        with caplog.at_level(logging.DEBUG):
            get_retry_request(
                request,
                spider=spider,
                reason=expected_reason,
                logger=logger,
            )
        assert (
            "custom-logger",
            logging.DEBUG,
            f"Retrying {request} (failed 1 times): {expected_reason}",
        ) in caplog.record_tuples

    def test_give_up_log_level_default(self, caplog: pytest.LogCaptureFixture) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        with caplog.at_level(logging.ERROR):
            get_retry_request(
                request,
                spider=spider,
                max_retry_times=0,
            )
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.ERROR,
            f"Gave up retrying {request} (failed 1 times): unspecified",
        ) in caplog.record_tuples

    def test_give_up_log_level_argument_name(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        with caplog.at_level(logging.WARNING):
            get_retry_request(
                request,
                spider=spider,
                max_retry_times=0,
                give_up_log_level="WARNING",
            )
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.WARNING,
            f"Gave up retrying {request} (failed 1 times): unspecified",
        ) in caplog.record_tuples

    def test_give_up_log_level_argument_number(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        request = Request("https://example.com")
        spider = self.get_spider()
        with caplog.at_level(logging.WARNING):
            get_retry_request(
                request,
                spider=spider,
                max_retry_times=0,
                give_up_log_level=logging.WARNING,
            )
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.WARNING,
            f"Gave up retrying {request} (failed 1 times): unspecified",
        ) in caplog.record_tuples

    def test_give_up_log_level_setting(self, caplog: pytest.LogCaptureFixture) -> None:
        request = Request("https://example.com")
        spider = self.get_spider({"RETRY_GIVE_UP_LOG_LEVEL": "WARNING"})
        with caplog.at_level(logging.WARNING):
            get_retry_request(
                request,
                spider=spider,
                max_retry_times=0,
            )
        assert (
            "scrapy.downloadermiddlewares.retry",
            logging.WARNING,
            f"Gave up retrying {request} (failed 1 times): unspecified",
        ) in caplog.record_tuples

    def test_give_up_log_level_invalid(self):
        request = Request("https://example.com")
        spider = self.get_spider()
        with pytest.raises(ValueError, match="Invalid give-up log level"):
            get_retry_request(
                request,
                spider=spider,
                max_retry_times=0,
                give_up_log_level="NOT_A_LEVEL",
            )

    def test_custom_stats_key(self):
        request = Request("https://example.com")
        spider = self.get_spider()
        expected_reason = "because"
        stats_key = "custom_retry"
        get_retry_request(
            request,
            spider=spider,
            reason=expected_reason,
            stats_base_key=stats_key,
        )
        for stat in (
            f"{stats_key}/count",
            f"{stats_key}/reason_count/{expected_reason}",
        ):
            assert spider.crawler.stats.get_value(stat) == 1
