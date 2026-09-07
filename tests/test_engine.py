from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest

from scrapy import signals
from scrapy.core.downloader import Downloader
from scrapy.core.engine import ExecutionEngine, _Slot
from scrapy.core.scheduler import BaseScheduler
from scrapy.exceptions import CloseSpider, DontCloseSpider, IgnoreRequest
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.misc import build_from_crawler
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
    from collections.abc import AsyncIterator, Generator

    from twisted.internet.defer import Deferred

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
        start_deferred = deferred_from_coro(e.start_async())
        with pytest.raises(RuntimeError, match="Engine already running"):
            yield deferred_from_coro(e.start_async())
        yield deferred_from_coro(e.stop_async())
        yield start_deferred

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
    scheduler = build_from_crawler(TestScheduler, crawler)

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


class ClosingPipeline:
    def open_spider(self):
        raise CloseSpider("pipeline_reason")


class TestCloseSpiderOnStartup:
    @coroutine_test
    async def test_pipeline(self, caplog: pytest.LogCaptureFixture) -> None:
        closed: list[str] = []

        def spider_closed(reason: str) -> None:
            closed.append(reason)

        crawler = get_crawler(DefaultSpider, {"ITEM_PIPELINES": {ClosingPipeline: 1}})
        crawler.signals.connect(spider_closed, signals.spider_closed)
        with caplog.at_level(logging.INFO):
            await crawler.crawl_async()
        assert crawler.stats.get_value("finish_reason") == "pipeline_reason"
        assert closed == ["pipeline_reason"]
        assert "Traceback" not in caplog.text

    @coroutine_test
    async def test_spider_opened(self) -> None:
        def spider_opened(spider: Spider) -> None:
            raise CloseSpider("signal_reason")

        crawler = get_crawler(DefaultSpider)
        crawler.signals.connect(spider_opened, signals.spider_opened)
        await crawler.crawl_async()
        assert crawler.stats.get_value("finish_reason") == "signal_reason"

    @coroutine_test
    async def test_startup_wins_over_spider_opened(self) -> None:
        def spider_opened(spider: Spider) -> None:
            raise CloseSpider("signal_reason")

        crawler = get_crawler(DefaultSpider, {"ITEM_PIPELINES": {ClosingPipeline: 1}})
        crawler.signals.connect(spider_opened, signals.spider_opened)
        await crawler.crawl_async()
        assert crawler.stats.get_value("finish_reason") == "pipeline_reason"

    @inline_callbacks_test
    def test_deferred_crawl(self) -> Generator[Deferred[Any], Any, None]:
        crawler = get_crawler(DefaultSpider, {"ITEM_PIPELINES": {ClosingPipeline: 1}})
        yield crawler.crawl()
        assert crawler.stats.get_value("finish_reason") == "pipeline_reason"


class TestMisuse:
    """The engine raises on operations that its state does not allow."""

    @coroutine_test
    async def test_stop_not_running(self) -> None:
        engine = ExecutionEngine(get_crawler(DefaultSpider), lambda _: None)
        try:
            with pytest.raises(RuntimeError, match="Engine not running"):
                await engine.stop_async()
        finally:
            await engine.close_async()

    def test_invalid_scheduler_class(self) -> None:
        class NotAScheduler:
            pass

        with pytest.raises(
            TypeError, match="does not fully implement the scheduler interface"
        ):
            ExecutionEngine(
                get_crawler(DefaultSpider, {"SCHEDULER": NotAScheduler}),
                lambda _: None,
            )

    @coroutine_test
    async def test_spider_is_idle_without_slot(self) -> None:
        engine = ExecutionEngine(get_crawler(DefaultSpider), lambda _: None)
        try:
            with pytest.raises(RuntimeError, match="Engine slot not assigned"):
                engine.spider_is_idle()
        finally:
            await engine.close_async()

    @coroutine_test
    async def test_crawl_without_spider(self) -> None:
        engine = ExecutionEngine(get_crawler(DefaultSpider), lambda _: None)
        try:
            with pytest.raises(RuntimeError, match="No open spider to crawl"):
                engine.crawl(Request("data:,"))
        finally:
            await engine.close_async()

    @coroutine_test
    async def test_open_spider_twice(self) -> None:
        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        engine = crawler.engine = ExecutionEngine(crawler, lambda _: None)
        await engine.open_spider_async()
        try:
            with pytest.raises(RuntimeError, match="No free spider slot"):
                await engine.open_spider_async()
        finally:
            await engine.close_async()


@coroutine_test
async def test_pause_unpause() -> None:
    engine = ExecutionEngine(get_crawler(DefaultSpider), lambda _: None)
    try:
        engine.pause()
        assert engine.paused
        engine.unpause()
        assert not engine.paused
    finally:
        await engine.close_async()


class TestSpiderIdle:
    @coroutine_test
    async def test_dont_close_spider(self) -> None:
        """A ``DontCloseSpider`` handler keeps the spider open for one more loop."""
        idle_calls = 0

        def spider_idle() -> None:
            nonlocal idle_calls
            idle_calls += 1
            if idle_calls == 1:
                # Schedule a request so that the engine loops again soon
                # instead of waiting for the slot heartbeat.
                crawler.engine.crawl(Request("data:,"))
                raise DontCloseSpider

        crawler = get_crawler(DefaultSpider)
        crawler.signals.connect(spider_idle, signals.spider_idle)
        await crawler.crawl_async()
        assert idle_calls == 2
        assert crawler.stats.get_value("finish_reason") == "finished"

    @coroutine_test
    async def test_not_idle_anymore(self) -> None:
        """A handler that schedules a request keeps the spider open."""
        urls: list[str] = []

        def spider_idle() -> None:
            if not urls:
                urls.append("data:,")
                crawler.engine.crawl(Request(urls[0]))

        crawler = get_crawler(DefaultSpider)
        crawler.signals.connect(spider_idle, signals.spider_idle)
        await crawler.crawl_async()
        assert crawler.stats.get_value("downloader/request_count") == 1


@coroutine_test
async def test_download_wrong_type(caplog: pytest.LogCaptureFixture) -> None:
    class WrongTypeDownloader(Downloader):
        def fetch(self, request: Request) -> str:  # type: ignore[override]
            return "not a response"

    class WrongTypeSpider(Spider):
        name = "wrong_type"

        async def start(self):
            yield Request("data:,")

    crawler = get_crawler(WrongTypeSpider, {"DOWNLOADER": WrongTypeDownloader})
    await crawler.crawl_async()
    assert "expected Response or Request, got <class 'str'>" in caplog.text


@coroutine_test
async def test_enqueue_scrape_error(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def enqueue_scrape(self, result, request):
        raise ValueError("enqueue error")

    monkeypatch.setattr("scrapy.core.engine.Scraper.enqueue_scrape", enqueue_scrape)

    class SimpleSpider(Spider):
        name = "simple"

        async def start(self):
            yield Request("data:,")

    crawler = get_crawler(SimpleSpider)
    await crawler.crawl_async()
    assert "Error while enqueuing scrape" in caplog.text
