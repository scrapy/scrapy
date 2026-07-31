from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from twisted.internet import defer
from twisted.python.failure import Failure

from scrapy import signals
from scrapy.core.engine import ExecutionEngine, _Slot
from scrapy.core.scheduler import BaseScheduler
from scrapy.exceptions import CloseSpider, DownloadCancelledError, IgnoreRequest
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.asyncio import sleep
from scrapy.utils.defer import (
    _schedule_coro,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.utils.bases.engine import TestEngineBase
from tests.utils.decorators import coroutine_test, inline_callbacks_test
from tests.utils.engine import (
    AttrsItemsSpider,
    CrawlerRun,
    DataClassItemsSpider,
    DictItemsSpider,
    MySpider,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tests.mockserver.http import MockServer


class DupeFilterSpider(MySpider):
    async def start(self):
        for url in self.start_urls:
            yield Request(url)  # no dont_filter=True


class ItemZeroDivisionErrorSpider(MySpider):
    custom_settings = {
        "ITEM_PIPELINES": {
            "tests.pipelines.ProcessWithZeroDivisionErrorPipeline": 300,
        }
    }


class ChangeCloseReasonSpider(MySpider):
    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = cls(*args, **kwargs)
        spider._set_crawler(crawler)
        crawler.signals.connect(spider.spider_idle, signals.spider_idle)
        return spider

    def spider_idle(self):
        raise CloseSpider(reason="custom_reason")


class TestEngine(TestEngineBase):
    @coroutine_test
    async def test_crawler(self, mockserver: MockServer) -> None:
        for spider in (
            MySpider,
            DictItemsSpider,
            AttrsItemsSpider,
            DataClassItemsSpider,
        ):
            run = CrawlerRun(spider)
            await run.run(mockserver)
            self._assert_visited_urls(run)
            self._assert_scheduled_requests(run, count=9)
            self._assert_downloaded_responses(run, count=9)
            self._assert_scraped_items(run)
            self._assert_signals_caught(run)
            self._assert_headers_received(run)
            self._assert_bytes_received(run)

    @coroutine_test
    async def test_crawler_dupefilter(self, mockserver: MockServer) -> None:
        run = CrawlerRun(DupeFilterSpider)
        await run.run(mockserver)
        self._assert_scheduled_requests(run, count=8)
        self._assert_dropped_requests(run)

    @coroutine_test
    async def test_crawler_itemerror(self, mockserver: MockServer) -> None:
        run = CrawlerRun(ItemZeroDivisionErrorSpider)
        await run.run(mockserver)
        self._assert_items_error(run)

    @coroutine_test
    async def test_crawler_change_close_reason_on_idle(
        self, mockserver: MockServer
    ) -> None:
        run = CrawlerRun(ChangeCloseReasonSpider)
        await run.run(mockserver)
        assert {
            "spider": run.crawler.spider,
            "reason": "custom_reason",
        } == run.signals_caught[signals.spider_closed]

    @coroutine_test
    async def test_close_downloader(self):
        e = ExecutionEngine(get_crawler(MySpider), lambda _: None)
        await e.close_async()

    def test_close_without_downloader(self):
        class CustomException(Exception):
            pass

        class BadDownloader:
            def __init__(self, crawler):
                raise CustomException

        with pytest.raises(CustomException):
            ExecutionEngine(
                get_crawler(MySpider, {"DOWNLOADER": BadDownloader}), lambda _: None
            )

    @inline_callbacks_test
    def test_start_already_running_exception(self):
        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        e = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = e
        yield deferred_from_coro(e.open_spider_async())
        _schedule_coro(e.start_async())
        with pytest.raises(RuntimeError, match="Engine already running"):
            yield deferred_from_coro(e.start_async())
        yield deferred_from_coro(e.stop_async())

    @coroutine_test
    async def test_stop_async_force_mode_not_supported(self) -> None:
        engine = ExecutionEngine(get_crawler(DefaultSpider), lambda _: None)

        with pytest.raises(ValueError, match="force stop mode is not supported"):
            await engine.stop_async(mode="force")

    @coroutine_test
    async def test_stop_async_not_running_raises(self) -> None:
        engine = ExecutionEngine(get_crawler(DefaultSpider), lambda _: None)

        with pytest.raises(RuntimeError, match="Engine not running"):
            await engine.stop_async()

    @coroutine_test
    async def test_stop_async_reentrant_fast_waits_for_closewait(self) -> None:
        engine = ExecutionEngine(get_crawler(DefaultSpider), lambda _: None)
        engine.spider = Mock()
        engine._stopping = True
        engine._closewait = defer.Deferred()

        with patch.object(
            engine, "close_spider_async", new_callable=AsyncMock
        ) as close:
            stop_dfd = deferred_from_coro(engine.stop_async(mode="fast"))
            await sleep(0)
            close.assert_called_once_with(reason="shutdown", mode="fast")
            assert not stop_dfd.called

            assert engine._closewait
            engine._closewait.callback(None)
            await maybe_deferred_to_future(stop_dfd)

    @coroutine_test
    async def test_stop_async_reentrant_graceful_without_spider_or_closewait(
        self,
    ) -> None:
        engine = ExecutionEngine(get_crawler(DefaultSpider), lambda _: None)
        engine._stopping = True

        with patch.object(
            engine, "close_spider_async", new_callable=AsyncMock
        ) as close:
            await engine.stop_async(mode="graceful")

        close.assert_not_called()

    @coroutine_test
    async def test_handle_downloader_output_ignores_fast_cancelled_failures(
        self,
    ) -> None:
        engine = ExecutionEngine(get_crawler(DefaultSpider), lambda _: None)
        engine.spider = Mock()
        engine._stop_mode = "fast"

        enqueue_scrape = Mock()
        engine.scraper.enqueue_scrape = enqueue_scrape  # type: ignore[method-assign]

        result = Failure(DownloadCancelledError("dropped during fast stop"))
        await maybe_deferred_to_future(
            engine._handle_downloader_output(result, Request("https://example.com"))
        )

        enqueue_scrape.assert_not_called()

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_start_already_running_exception_asyncio(self):
        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        e = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = e
        await e.open_spider_async()
        with pytest.raises(RuntimeError, match="Engine already running"):
            await asyncio.gather(e.start_async(), e.start_async())
        await e.stop_async()

    @coroutine_test
    async def test_start_request_processing_exception(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class BadRequestFingerprinter:
            def fingerprint(self, request):
                raise ValueError  # to make Scheduler.enqueue_request() fail

        class SimpleSpider(Spider):
            name = "simple"

            async def start(self):
                yield Request("data:,")

        crawler = get_crawler(
            SimpleSpider, {"REQUEST_FINGERPRINTER_CLASS": BadRequestFingerprinter}
        )
        with caplog.at_level(logging.DEBUG):
            await crawler.crawl_async()
        assert "Error while processing requests from start()" in caplog.text
        assert "Spider closed (shutdown)" in caplog.text

    def test_short_timeout(self):
        args = (
            sys.executable,
            "-m",
            "scrapy.cmdline",
            "fetch",
            "-s",
            "CLOSESPIDER_TIMEOUT=0.001",
            "-s",
            "LOG_LEVEL=DEBUG",
            "http://toscrape.com",
        )
        p = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        try:
            _, stderr = p.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            pytest.fail("Command took too much time to complete")

        stderr_str = stderr.decode("utf-8")
        assert "AttributeError" not in stderr_str, stderr_str
        assert "AssertionError" not in stderr_str, stderr_str


@coroutine_test
async def test_request_scheduled_signal():
    class TestScheduler(BaseScheduler):
        def __init__(self) -> None:
            self.enqueued: list[Request] = []

        def enqueue_request(self, request: Request) -> bool:
            self.enqueued.append(request)
            return True

    def signal_handler(request: Request, spider: Spider) -> None:
        if "drop" in request.url:
            raise IgnoreRequest

    crawler = get_crawler(MySpider)
    engine = ExecutionEngine(crawler, lambda _: None)
    scheduler = TestScheduler()  # type: ignore[abstract]

    async def start() -> AsyncIterator[Any]:
        return
        yield

    engine._start = start()
    engine._slot = _Slot(False, Mock(), scheduler)
    crawler.signals.connect(signal_handler, signals.request_scheduled)
    keep_request = Request("https://keep.example")
    engine._schedule_request(keep_request)
    drop_request = Request("https://drop.example")
    engine._schedule_request(drop_request)
    assert scheduler.enqueued == [keep_request], (
        f"{scheduler.enqueued!r} != [{keep_request!r}]"
    )
    crawler.signals.disconnect(signal_handler, signals.request_scheduled)
