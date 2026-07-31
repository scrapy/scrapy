from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import pytest
from twisted.internet import defer

from scrapy import Request, signals
from scrapy.core.engine import ExecutionEngine
from scrapy.statscollectors import MemoryStatsCollector
from scrapy.utils.asyncio import sleep
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy.core.scheduler import Scheduler
    from scrapy.crawler import Crawler


@pytest.fixture
def crawler() -> Crawler:
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    return crawler


@coroutine_test
async def test_no_slot(crawler: Crawler) -> None:
    engine = ExecutionEngine(crawler, lambda _: None)
    crawler.engine = engine
    await engine.open_spider_async()
    slot = engine._slot
    engine._slot = None
    with pytest.raises(RuntimeError, match="Engine slot not assigned"):
        await engine.close_spider_async()
    # close it correctly
    engine._slot = slot
    await engine.close_spider_async()


@coroutine_test
async def test_no_spider(crawler: Crawler) -> None:
    engine = ExecutionEngine(crawler, lambda _: None)
    with pytest.raises(RuntimeError, match="Spider not opened"):
        await engine.close_spider_async()
    engine.downloader.close()  # cleanup


@coroutine_test
async def test_exception_slot(
    crawler: Crawler, caplog: pytest.LogCaptureFixture
) -> None:
    engine = ExecutionEngine(crawler, lambda _: None)
    crawler.engine = engine
    await engine.open_spider_async()
    assert engine._slot
    del engine._slot.heartbeat
    await engine.close_spider_async()
    assert "Slot close failure" in caplog.text


@coroutine_test
async def test_exception_downloader(
    crawler: Crawler, caplog: pytest.LogCaptureFixture
) -> None:
    engine = ExecutionEngine(crawler, lambda _: None)
    crawler.engine = engine
    await engine.open_spider_async()
    engine.downloader.close = Mock(  # type: ignore[method-assign]
        side_effect=Exception("close failed")
    )
    await engine.close_spider_async()
    assert "Downloader close failure" in caplog.text


@coroutine_test
async def test_exception_scraper(
    crawler: Crawler, caplog: pytest.LogCaptureFixture
) -> None:
    engine = ExecutionEngine(crawler, lambda _: None)
    crawler.engine = engine
    await engine.open_spider_async()
    engine.scraper.slot = None
    await engine.close_spider_async()
    assert "Scraper close failure" in caplog.text


@coroutine_test
async def test_exception_scheduler(
    crawler: Crawler, caplog: pytest.LogCaptureFixture
) -> None:
    engine = ExecutionEngine(crawler, lambda _: None)
    crawler.engine = engine
    await engine.open_spider_async()
    assert engine._slot
    del cast("Scheduler", engine._slot.scheduler).dqs
    await engine.close_spider_async()
    assert "Scheduler close failure" in caplog.text


@coroutine_test
async def test_exception_signal(
    crawler: Crawler, caplog: pytest.LogCaptureFixture
) -> None:
    engine = ExecutionEngine(crawler, lambda _: None)
    crawler.engine = engine
    await engine.open_spider_async()
    signal_manager = engine.signals
    del engine.signals
    await engine.close_spider_async()
    assert "Error while sending spider_close signal" in caplog.text
    # send the spider_closed signal to close various components
    await signal_manager.send_catch_log_async(
        signal=signals.spider_closed,
        spider=engine.spider,
        reason="cancelled",
    )


@coroutine_test
async def test_exception_stats(
    crawler: Crawler, caplog: pytest.LogCaptureFixture
) -> None:
    engine = ExecutionEngine(crawler, lambda _: None)
    crawler.engine = engine
    await engine.open_spider_async()
    assert isinstance(crawler.stats, MemoryStatsCollector)
    del crawler.stats.spider_stats
    await engine.close_spider_async()
    assert "Stats close failure" in caplog.text


@coroutine_test
async def test_exception_callback(
    crawler: Crawler, caplog: pytest.LogCaptureFixture
) -> None:
    engine = ExecutionEngine(crawler, lambda _: defer.fail(ValueError()))
    crawler.engine = engine
    await engine.open_spider_async()
    await engine.close_spider_async()
    assert "Error running spider_closed_callback" in caplog.text


@coroutine_test
async def test_exception_async_callback(
    crawler: Crawler, caplog: pytest.LogCaptureFixture
) -> None:
    async def cb(_):
        raise ValueError

    engine = ExecutionEngine(crawler, cb)
    crawler.engine = engine
    await engine.open_spider_async()
    await engine.close_spider_async()
    assert "Error running spider_closed_callback" in caplog.text


@coroutine_test
async def test_waits_for_in_flight_enqueues(crawler: Crawler) -> None:
    """An enqueue that is still in flight when the spider closes is awaited
    before the scheduler is closed, and the closing engine starts no request
    while it waits."""
    engine = ExecutionEngine(crawler, lambda _: None)
    crawler.engine = engine
    await engine.open_spider_async()
    assert engine._slot is not None
    # As when close_spider_async() is reached without stopping the engine
    # first, e.g. from the closespider extension or a CloseSpider exception.
    engine.running = True
    scheduler = engine._slot.scheduler

    started: defer.Deferred[None] = defer.Deferred()
    stored: defer.Deferred[None] = defer.Deferred()
    events: list[str] = []

    async def enqueue_request_async(request: Request) -> bool:
        # Stored right away, so that a scheduling round running while this
        # enqueue is still in flight would find something to send.
        scheduler.enqueue_request(request)
        started.callback(None)
        await maybe_deferred_to_future(stored)
        events.append("enqueued")
        return True

    scheduler_close = scheduler.close

    def close(reason: str) -> defer.Deferred[None] | None:
        events.append("scheduler closed")
        return scheduler_close(reason)

    scheduler.enqueue_request_async = enqueue_request_async  # type: ignore[attr-defined]
    scheduler.close = close  # type: ignore[method-assign]
    engine._scheduler_enqueues_async = True
    engine._schedule_request(Request("data:,"))
    assert engine._scheduling

    closing = deferred_from_coro(engine.close_spider_async())
    # Let the enqueue store its request and the closing engine reach the point
    # where it waits for that enqueue.
    await maybe_deferred_to_future(started)
    await sleep(0)
    assert engine._slot.closing is not None, "the slot is not marked as closing"
    engine._start_scheduled_requests()
    assert not engine._slot.inprogress, "a closing engine started a request"
    assert not closing.called

    stored.callback(None)
    await maybe_deferred_to_future(closing)
    assert events == ["enqueued", "scheduler closed"]


@coroutine_test
async def test_exception_in_flight_enqueue(
    crawler: Crawler, caplog: pytest.LogCaptureFixture
) -> None:
    """An in-flight enqueue that fails does not keep the scheduler from being
    closed, and hence its pending requests from being persisted."""
    engine = ExecutionEngine(crawler, lambda _: None)
    crawler.engine = engine
    await engine.open_spider_async()
    assert engine._slot is not None
    engine.running = True
    scheduler = engine._slot.scheduler
    events: list[str] = []

    scheduler_close = scheduler.close

    def close(reason: str) -> defer.Deferred[None] | None:
        events.append("scheduler closed")
        return scheduler_close(reason)

    scheduler.close = close  # type: ignore[method-assign]

    # A tracked enqueue that ends in a failure, as the tail of
    # _enqueue_request_async() does when it cannot reschedule the loop.
    failed: defer.Deferred[None] = defer.Deferred()
    failed.errback(Exception("enqueue failed"))
    engine._scheduling.add(failed)

    await engine.close_spider_async()
    assert "Pending request scheduling failure" in caplog.text
    assert events == ["scheduler closed"]
