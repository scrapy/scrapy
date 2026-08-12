from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scrapy import Request, Spider
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    import pytest


class _BaseSpiderMiddleware:
    def __init__(self, crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)


class LogExceptionMiddleware(_BaseSpiderMiddleware):
    def process_spider_exception(self, response, exception):
        self.crawler.spider.logger.info(
            "Middleware: %s exception caught", exception.__class__.__name__
        )


# ================================================================================
# (0) recover from an exception on a spider callback
class RecoveryMiddleware(_BaseSpiderMiddleware):
    def process_spider_exception(self, response, exception):
        self.crawler.spider.logger.info(
            "Middleware: %s exception caught", exception.__class__.__name__
        )
        return [
            {"from": "process_spider_exception"},
            Request(response.url, meta={"dont_fail": True}, dont_filter=True),
        ]


class RecoverySpider(Spider):
    name = "RecoverySpider"
    custom_settings = {
        "SPIDER_MIDDLEWARES_BASE": {},
        "SPIDER_MIDDLEWARES": {
            RecoveryMiddleware: 10,
        },
    }

    async def start(self):
        yield Request(self.mockserver.url("/status?n=200"))

    def parse(self, response):
        yield {"test": 1}
        self.logger.info("DONT_FAIL: %s", response.meta.get("dont_fail"))
        if not response.meta.get("dont_fail"):
            raise TabError


class RecoveryAsyncGenSpider(RecoverySpider):
    name = "RecoveryAsyncGenSpider"

    async def parse(self, response):
        for r in super().parse(response):
            yield r


# ================================================================================
# (1) exceptions from a spider middleware's process_spider_input method
class FailProcessSpiderInputMiddleware(_BaseSpiderMiddleware):
    def process_spider_input(self, response):
        self.crawler.spider.logger.info("Middleware: will raise IndexError")
        raise IndexError


class ProcessSpiderInputSpiderWithoutErrback(Spider):
    name = "ProcessSpiderInputSpiderWithoutErrback"
    custom_settings = {
        "SPIDER_MIDDLEWARES": {
            # spider
            FailProcessSpiderInputMiddleware: 8,
            LogExceptionMiddleware: 6,
            # engine
        }
    }

    async def start(self):
        yield Request(url=self.mockserver.url("/status?n=200"), callback=self.parse)

    def parse(self, response):
        return {"from": "callback"}


class ProcessSpiderInputSpiderWithErrback(ProcessSpiderInputSpiderWithoutErrback):
    name = "ProcessSpiderInputSpiderWithErrback"

    async def start(self):
        yield Request(
            self.mockserver.url("/status?n=200"), self.parse, errback=self.errback
        )

    def errback(self, failure):
        self.logger.info("Got a Failure on the Request errback")
        return {"from": "errback"}


# ================================================================================
# (2) exceptions from a spider callback (generator)
class GeneratorCallbackSpider(Spider):
    name = "GeneratorCallbackSpider"
    custom_settings = {
        "SPIDER_MIDDLEWARES": {
            LogExceptionMiddleware: 10,
        },
    }

    async def start(self):
        yield Request(self.mockserver.url("/status?n=200"))

    def parse(self, response):
        yield {"test": 1}
        yield {"test": 2}
        raise ImportError


class AsyncGeneratorCallbackSpider(GeneratorCallbackSpider):
    async def parse(self, response):
        yield {"test": 1}
        yield {"test": 2}
        raise ImportError


# ================================================================================
# (2.1) exceptions from a spider callback (generator, middleware right after callback)
class GeneratorCallbackSpiderMiddlewareRightAfterSpider(GeneratorCallbackSpider):
    name = "GeneratorCallbackSpiderMiddlewareRightAfterSpider"
    custom_settings = {
        "SPIDER_MIDDLEWARES": {
            LogExceptionMiddleware: 100000,
        },
    }


# ================================================================================
# (3) exceptions from a spider callback (not a generator)
class NotGeneratorCallbackSpider(Spider):
    name = "NotGeneratorCallbackSpider"
    custom_settings = {
        "SPIDER_MIDDLEWARES": {
            LogExceptionMiddleware: 10,
        },
    }

    async def start(self):
        yield Request(self.mockserver.url("/status?n=200"))

    def parse(self, response):
        return [{"test": 1}, {"test": 1 / 0}]


# ================================================================================
# (3.1) exceptions from a spider callback (not a generator, middleware right after callback)
class NotGeneratorCallbackSpiderMiddlewareRightAfterSpider(NotGeneratorCallbackSpider):
    name = "NotGeneratorCallbackSpiderMiddlewareRightAfterSpider"
    custom_settings = {
        "SPIDER_MIDDLEWARES": {
            LogExceptionMiddleware: 100000,
        },
    }


# ================================================================================
# (4) exceptions from a middleware process_spider_output method (generator)
class _GeneratorDoNothingMiddleware(_BaseSpiderMiddleware):
    async def process_spider_output(self, response, result):
        async for r in result:
            r["processed"].append(f"{self.__class__.__name__}.process_spider_output")
            yield r

    def process_spider_exception(self, response, exception):
        method = f"{self.__class__.__name__}.process_spider_exception"
        self.crawler.spider.logger.info(
            "%s: %s caught", method, exception.__class__.__name__
        )


class GeneratorFailMiddleware(_BaseSpiderMiddleware):
    async def process_spider_output(self, response, result):
        async for r in result:
            r["processed"].append(f"{self.__class__.__name__}.process_spider_output")
            yield r
            raise LookupError

    def process_spider_exception(self, response, exception):
        method = f"{self.__class__.__name__}.process_spider_exception"
        self.crawler.spider.logger.info(
            "%s: %s caught", method, exception.__class__.__name__
        )
        yield {"processed": [method]}


class GeneratorDoNothingAfterFailureMiddleware(_GeneratorDoNothingMiddleware):
    pass


class GeneratorRecoverMiddleware(_BaseSpiderMiddleware):
    async def process_spider_output(self, response, result):
        async for r in result:
            r["processed"].append(f"{self.__class__.__name__}.process_spider_output")
            yield r

    def process_spider_exception(self, response, exception):
        method = f"{self.__class__.__name__}.process_spider_exception"
        self.crawler.spider.logger.info(
            "%s: %s caught", method, exception.__class__.__name__
        )
        yield {"processed": [method]}


class GeneratorDoNothingAfterRecoveryMiddleware(_GeneratorDoNothingMiddleware):
    pass


class GeneratorOutputChainSpider(Spider):
    name = "GeneratorOutputChainSpider"
    custom_settings = {
        "SPIDER_MIDDLEWARES": {
            GeneratorFailMiddleware: 10,
            GeneratorDoNothingAfterFailureMiddleware: 8,
            GeneratorRecoverMiddleware: 5,
            GeneratorDoNothingAfterRecoveryMiddleware: 3,
        },
    }

    async def start(self):
        yield Request(self.mockserver.url("/status?n=200"))

    def parse(self, response):
        yield {"processed": ["parse-first-item"]}
        yield {"processed": ["parse-second-item"]}


# ================================================================================
# (5) errback output after a download error
class LogOutputMiddleware(_BaseSpiderMiddleware):
    async def process_spider_output(self, response, result):
        async for o in result:
            self.crawler.spider.logger.info(
                f"Middleware: output {o} with response {response}"
            )
            yield o

    def process_spider_exception(self, response, exception):
        self.crawler.spider.logger.info(
            f"Middleware: {exception.__class__.__name__} exception caught"
            f" with response {response}"
        )
        return []


class DownloadErrorSpider(Spider):
    name = "DownloadErrorSpider"
    custom_settings = {
        "SPIDER_MIDDLEWARES": {
            LogOutputMiddleware: 10,
        },
    }

    async def start(self):
        yield Request(self.mockserver.url("/drop?abort=1"), errback=self.errback)

    def errback(self, failure):
        yield {"from": "errback"}
        yield Request(self.mockserver.url("/status?n=200"), callback=self.parse)

    def parse(self, response):
        self.logger.info(f"is_start_request: {response.meta.get('is_start_request')}")


class DownloadErrorFailSpider(DownloadErrorSpider):
    name = "DownloadErrorFailSpider"

    def errback(self, failure):
        yield {"from": "errback"}
        raise LookupError


# ================================================================================
class TestSpiderMiddleware:
    mockserver: MockServer

    @classmethod
    def setup_class(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def teardown_class(cls):
        cls.mockserver.__exit__(None, None, None)

    async def crawl_log(
        self, spider: type[Spider], caplog: pytest.LogCaptureFixture
    ) -> str:
        crawler = get_crawler(spider)
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            await crawler.crawl_async(mockserver=self.mockserver)
        return caplog.text

    @coroutine_test
    async def test_recovery(self, caplog: pytest.LogCaptureFixture) -> None:
        """
        (0) Recover from an exception in a spider callback. The final item count should be 3
        (one yielded from the callback method before the exception is raised, one directly
        from the recovery middleware and one from the spider when processing the request that
        was enqueued from the recovery middleware)
        """
        log = await self.crawl_log(RecoverySpider, caplog)
        assert "Middleware: TabError exception caught" in log
        assert log.count("Middleware: TabError exception caught") == 1
        assert "'item_scraped_count': 3" in log

    @coroutine_test
    async def test_recovery_asyncgen(self, caplog: pytest.LogCaptureFixture) -> None:
        """
        Same as test_recovery but with an async callback.
        """
        log = await self.crawl_log(RecoveryAsyncGenSpider, caplog)
        assert "Middleware: TabError exception caught" in log
        assert log.count("Middleware: TabError exception caught") == 1
        assert "'item_scraped_count': 3" in log

    @coroutine_test
    async def test_process_spider_input_without_errback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        (1.1) An exception from the process_spider_input chain should be caught by the
        process_spider_exception chain from the start if the Request has no errback
        """
        log1 = await self.crawl_log(ProcessSpiderInputSpiderWithoutErrback, caplog)
        assert "Middleware: will raise IndexError" in log1
        assert "Middleware: IndexError exception caught" in log1

    @coroutine_test
    async def test_process_spider_input_with_errback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        (1.2) An exception from the process_spider_input chain should not be caught by the
        process_spider_exception chain if the Request has an errback
        """
        log1 = await self.crawl_log(ProcessSpiderInputSpiderWithErrback, caplog)
        assert "Middleware: IndexError exception caught" not in log1
        assert "Middleware: will raise IndexError" in log1
        assert "Got a Failure on the Request errback" in log1
        assert "{'from': 'errback'}" in log1
        assert "{'from': 'callback'}" not in log1
        assert "'item_scraped_count': 1" in log1

    @coroutine_test
    async def test_generator_callback(self, caplog: pytest.LogCaptureFixture) -> None:
        """
        (2) An exception from a spider callback (returning a generator) should
        be caught by the process_spider_exception chain. Items yielded before the
        exception is raised should be processed normally.
        """
        log2 = await self.crawl_log(GeneratorCallbackSpider, caplog)
        assert "Middleware: ImportError exception caught" in log2
        assert "'item_scraped_count': 2" in log2

    @coroutine_test
    async def test_async_generator_callback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        Same as test_generator_callback but with an async callback.
        """
        log2 = await self.crawl_log(AsyncGeneratorCallbackSpider, caplog)
        assert "Middleware: ImportError exception caught" in log2
        assert "'item_scraped_count': 2" in log2

    @coroutine_test
    async def test_generator_callback_right_after_callback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        (2.1) Special case of (2): Exceptions should be caught
        even if the middleware is placed right after the spider
        """
        log21 = await self.crawl_log(
            GeneratorCallbackSpiderMiddlewareRightAfterSpider, caplog
        )
        assert "Middleware: ImportError exception caught" in log21
        assert "'item_scraped_count': 2" in log21

    @coroutine_test
    async def test_not_a_generator_callback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        (3) An exception from a spider callback (returning a list) should
        be caught by the process_spider_exception chain. No items should be processed.
        """
        log3 = await self.crawl_log(NotGeneratorCallbackSpider, caplog)
        assert "Middleware: ZeroDivisionError exception caught" in log3
        assert "item_scraped_count" not in log3

    @coroutine_test
    async def test_not_a_generator_callback_right_after_callback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        (3.1) Special case of (3): Exceptions should be caught
        even if the middleware is placed right after the spider
        """
        log31 = await self.crawl_log(
            NotGeneratorCallbackSpiderMiddlewareRightAfterSpider, caplog
        )
        assert "Middleware: ZeroDivisionError exception caught" in log31
        assert "item_scraped_count" not in log31

    @coroutine_test
    async def test_generator_output_chain(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        (4) An exception from a middleware's process_spider_output method should be sent
        to the process_spider_exception method from the next middleware in the chain.
        The result of the recovery by the process_spider_exception method should be handled
        by the process_spider_output method from the next middleware.
        The final item count should be 2 (one from the spider callback and one from the
        process_spider_exception chain)
        """
        log4 = await self.crawl_log(GeneratorOutputChainSpider, caplog)
        assert "'item_scraped_count': 2" in log4
        assert (
            "GeneratorRecoverMiddleware.process_spider_exception: LookupError caught"
            in log4
        )
        assert (
            "GeneratorDoNothingAfterFailureMiddleware.process_spider_exception: LookupError caught"
            in log4
        )
        assert (
            "GeneratorFailMiddleware.process_spider_exception: LookupError caught"
            not in log4
        )
        assert (
            "GeneratorDoNothingAfterRecoveryMiddleware.process_spider_exception: LookupError caught"
            not in log4
        )
        item_from_callback = {
            "processed": [
                "parse-first-item",
                "GeneratorFailMiddleware.process_spider_output",
                "GeneratorDoNothingAfterFailureMiddleware.process_spider_output",
                "GeneratorRecoverMiddleware.process_spider_output",
                "GeneratorDoNothingAfterRecoveryMiddleware.process_spider_output",
            ]
        }
        item_recovered = {
            "processed": [
                "GeneratorRecoverMiddleware.process_spider_exception",
                "GeneratorDoNothingAfterRecoveryMiddleware.process_spider_output",
            ]
        }
        assert str(item_from_callback) in log4
        assert str(item_recovered) in log4
        assert "parse-second-item" not in log4

    @coroutine_test
    async def test_download_error_errback_output(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        (5.1) The output of an errback called because a download failed goes
        through the process_spider_output chain, with None as the response.
        """
        log5 = await self.crawl_log(DownloadErrorSpider, caplog)
        assert "Middleware: output {'from': 'errback'} with response None" in log5
        assert "'item_scraped_count': 1" in log5
        assert "Crawled (200)" in log5
        assert "is_start_request: None" in log5

    @coroutine_test
    async def test_download_error_errback_exception(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        (5.2) An exception from such an errback goes through the
        process_spider_exception chain.
        """
        log5 = await self.crawl_log(DownloadErrorFailSpider, caplog)
        assert "Middleware: output {'from': 'errback'} with response None" in log5
        assert "Middleware: LookupError exception caught with response None" in log5
        assert "'item_scraped_count': 1" in log5
