from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock

import pytest
from twisted.internet.defer import Deferred

from scrapy import signals
from scrapy.core.engine import ExecutionEngine, _Slot
from scrapy.core.scheduler import BaseScheduler
from scrapy.exceptions import CloseSpider, IgnoreRequest
from scrapy.http import Request
from scrapy.spiders import Spider
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


class TestEngineThrottler:
    @pytest.fixture
    def engine(self):
        crawler = get_crawler(MySpider)
        engine = ExecutionEngine(crawler, lambda _: None)
        yield engine
        engine.downloader.close()

    def test_pause_cancels_delay_wakeup(self, engine):
        wakeup = Mock()
        engine._delay_wakeup = wakeup
        engine.pause()
        assert engine.paused is True
        wakeup.cancel.assert_called_once_with()
        assert engine._delay_wakeup is None
        engine.unpause()
        assert engine.paused is False

    def test_unpause_reruns_the_loop(self, engine):
        engine._slot = Mock()
        engine.pause()
        # Pausing stops the loop from re-running itself, so unpausing must kick
        # it, or a crawl held only by a time-based limit would stall.
        engine.unpause()
        engine._slot.nextcall.schedule.assert_called_once_with()

    @pytest.mark.requires_reactor  # call_later() needs a reactor or asyncio loop
    def test_maybe_arm_delay_wakeup_arms_timer(self, engine):
        engine._get_next_request_delay = lambda: 5.0
        engine._slot = Mock()
        engine._slot.scheduler.has_pending_requests.return_value = True
        engine._maybe_arm_delay_wakeup()
        assert engine._delay_wakeup is not None
        # Cancel the scheduled reactor call so it does not leak into other tests.
        engine._cancel_delay_wakeup()

    def test_maybe_arm_delay_wakeup_no_delay(self, engine):
        engine._get_next_request_delay = lambda: None
        engine._slot = Mock()
        engine._slot.scheduler.has_pending_requests.return_value = True
        engine._maybe_arm_delay_wakeup()
        assert engine._delay_wakeup is None

    def test_maybe_arm_delay_wakeup_zero_delay(self, engine):
        # A 0 delay means a request is ready but could not be sent (e.g. the
        # downloader is at capacity); arming a 0-second timer would busy-loop
        # the engine, so no timer must be armed.
        engine._get_next_request_delay = lambda: 0.0
        engine._slot = Mock()
        engine._slot.scheduler.has_pending_requests.return_value = True
        engine._maybe_arm_delay_wakeup()
        assert engine._delay_wakeup is None

    def test_maybe_arm_delay_wakeup_not_supported(self, engine):
        # A scheduler without get_next_request_delay never arms a timer.
        engine._get_next_request_delay = None
        engine._slot = Mock()
        engine._slot.scheduler.has_pending_requests.return_value = True
        engine._maybe_arm_delay_wakeup()
        assert engine._delay_wakeup is None

    def test_maybe_warn_throttler_backout(self, engine, caplog):
        # A scheduler without get_next_request_delay is not throttler-aware, so
        # the warning recommends switching to one.
        engine._get_next_request_delay = None
        engine._throttler_waiting = {Request("http://a.example"): False}
        with caplog.at_level(logging.WARNING, logger="scrapy.core.engine"):
            engine._maybe_warn_throttler_backout()
            # A second call is a no-op (the warning is emitted only once).
            engine._maybe_warn_throttler_backout()
        assert engine._throttler_backout_warned is True
        assert caplog.text.count("ThrottlerAwareScheduler") == 1

    def test_maybe_warn_throttler_backout_throttler_aware(self, engine, caplog):
        # A throttler-aware scheduler (one with get_next_request_delay) holds
        # throttled requests itself, so no warning is emitted.
        engine._get_next_request_delay = lambda: None
        engine._throttler_waiting = {Request("http://a.example"): False}
        with caplog.at_level(logging.WARNING, logger="scrapy.core.engine"):
            engine._maybe_warn_throttler_backout()
        assert engine._throttler_backout_warned is False
        assert "ThrottlerAwareScheduler" not in caplog.text

    def test_maybe_warn_throttler_backout_unscheduled_only(self, engine, caplog):
        # Unscheduled requests never went through the scheduler, so no
        # scheduler can hold them back and recommending a different one would be
        # misleading.
        engine._get_next_request_delay = None
        engine._throttler_waiting = {Request("http://a.example"): True}
        with caplog.at_level(logging.WARNING, logger="scrapy.core.engine"):
            engine._maybe_warn_throttler_backout()
        assert engine._throttler_backout_warned is False
        assert "ThrottlerAwareScheduler" not in caplog.text
        # One request from the scheduler among them is enough to warn.
        engine._throttler_waiting[Request("http://b.example")] = False
        with caplog.at_level(logging.WARNING, logger="scrapy.core.engine"):
            engine._maybe_warn_throttler_backout()
        assert engine._throttler_backout_warned is True
        assert caplog.text.count("ThrottlerAwareScheduler") == 1

    @coroutine_test
    async def test_acquire_throttler_reruns_the_loop_for_unscheduled(self, engine):
        engine._slot = Mock()
        engine.crawler.throttler = Mock()
        engine.crawler.throttler.acquire = AsyncMock()
        request = Request("http://a.example")

        await maybe_deferred_to_future(engine._acquire_throttler(request, False))
        # A request from the scheduler goes on to the downloader, whose own
        # finally block re-runs the loop once it is done with it.
        engine._slot.nextcall.schedule.assert_not_called()

        await maybe_deferred_to_future(engine._acquire_throttler(request, True))
        # An unscheduled request stops claiming the free slots of its scopes
        # here, which can be what lets a request that shares them through.
        engine._slot.nextcall.schedule.assert_called_once_with()

    def test_spider_is_idle_false_while_scheduling(self, engine):
        engine._slot = Mock()
        engine.scraper.slot = Mock()
        engine.scraper.slot.is_idle.return_value = True
        engine.downloader = Mock()
        engine.downloader.active = []
        engine._throttler_waiting = {}
        engine._start = None
        engine._scheduling = {Deferred()}
        # An in-flight async enqueue keeps the spider from being considered idle.
        assert engine.spider_is_idle() is False

    @coroutine_test
    async def test_enqueue_request_async_dropped(self, engine):
        scheduler = Mock()

        async def enqueue_request_async(request):
            return False

        scheduler.enqueue_request_async = enqueue_request_async
        engine._slot = Mock()
        engine._slot.scheduler = scheduler
        engine.spider = Mock()
        dropped = []

        def on_dropped(request, spider):
            dropped.append(request)

        engine.signals.connect(on_dropped, signals.request_dropped, weak=False)
        request = Request("http://a.example")
        await engine._enqueue_request_async(request)
        assert dropped == [request]
        engine._slot.nextcall.schedule.assert_called_once_with()

    @coroutine_test
    async def test_enqueue_request_async_error(self, engine, caplog):
        scheduler = Mock()

        async def enqueue_request_async(request):
            raise RuntimeError("boom")

        scheduler.enqueue_request_async = enqueue_request_async
        engine._slot = Mock()
        engine._slot.scheduler = scheduler
        engine.spider = Mock()
        with caplog.at_level(logging.ERROR, logger="scrapy.core.engine"):
            await engine._enqueue_request_async(Request("http://a.example"))
        assert "Error while enqueuing request" in caplog.text
        engine._slot.nextcall.schedule.assert_called_once_with()

    @coroutine_test
    async def test_enqueue_request_async_without_slot(self, engine):
        # The spider was closed before the enqueue coroutine got to run, so
        # there is no scheduler left to enqueue into.
        engine._slot = None
        await engine._enqueue_request_async(Request("http://a.example"))

    @coroutine_test
    async def test_enqueue_request_async_slot_gone(self, engine):
        scheduler = Mock()

        async def enqueue_request_async(request):
            # The spider is closed while the enqueue is in flight.
            engine._slot = None
            return True

        scheduler.enqueue_request_async = enqueue_request_async
        slot = Mock()
        slot.scheduler = scheduler
        engine._slot = slot
        engine.spider = Mock()
        await engine._enqueue_request_async(Request("http://a.example"))
        # No reschedule is attempted once the slot is gone.
        slot.nextcall.schedule.assert_not_called()

    @coroutine_test
    async def test_schedule_request_tracks_the_enqueue(self, engine):
        stored: Deferred[bool] = Deferred()

        async def enqueue_request_async(request):
            return await maybe_deferred_to_future(stored)

        scheduler = Mock()
        scheduler.enqueue_request_async = enqueue_request_async
        engine._slot = Mock()
        engine._slot.scheduler = scheduler
        engine.spider = Mock()
        # The request_scheduled receivers are irrelevant here, and they expect a
        # crawl that actually started.
        engine.signals.disconnect_all(signals.request_scheduled)
        engine._scheduler_enqueues_async = True
        engine._schedule_request(Request("http://a.example"))
        # An enqueue is tracked for as long as it is in flight, so that neither
        # spider_is_idle() nor close_spider() gets ahead of it.
        assert len(engine._scheduling) == 1
        tracked = next(iter(engine._scheduling))
        stored.callback(True)
        await maybe_deferred_to_future(tracked)
        assert not engine._scheduling
