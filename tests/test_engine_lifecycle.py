from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest
from twisted.internet.defer import Deferred

from scrapy import Request, signals
from scrapy.core.engine import EngineState, ExecutionEngine
from scrapy.core.scheduler import BaseScheduler
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.defer import (
    _schedule_coro,
    deferred_from_coro,
    maybe_deferred_to_future,
)
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import Callable

    from scrapy.crawler import Crawler
    from scrapy.utils._stopmode import _StopMode


class SignalRecorder:
    """Record lifecycle signals and the engine state at the time each signal
    fired."""

    SIGNALS = ("engine_started", "engine_stopped", "spider_opened", "spider_closed")

    def __init__(self, crawler: Crawler) -> None:
        self.crawler = crawler
        self.calls: list[tuple[str, EngineState]] = []
        self.close_reasons: list[str] = []
        # Keep strong references to the handlers: signal connections are weak.
        self._handlers = [self._make_handler(name) for name in self.SIGNALS]
        for name, handler in zip(self.SIGNALS, self._handlers, strict=True):
            crawler.signals.connect(handler, getattr(signals, name))

    def _make_handler(self, name: str) -> Callable[..., None]:
        def handler(**kwargs: Any) -> None:
            assert self.crawler.engine is not None
            self.calls.append((name, self.crawler.engine.state))
            if name == "spider_closed":
                self.close_reasons.append(kwargs["reason"])

        return handler

    @property
    def names(self) -> list[str]:
        return [call[0] for call in self.calls]

    @property
    def states(self) -> list[EngineState]:
        return [call[1] for call in self.calls]


class BlockingScheduler(BaseScheduler):
    """A scheduler whose close() blocks until unblocked, to keep the engine
    deterministically in the SPIDER_CLOSING state."""

    def __init__(self) -> None:
        self.entered_close: Deferred[None] = Deferred()
        self.unblock_close: Deferred[None] = Deferred()

    def has_pending_requests(self) -> bool:
        return False

    def enqueue_request(self, request: Any) -> bool:
        return True

    def next_request(self) -> Any:
        return None

    def close(self, reason: str) -> Deferred[None]:
        self.entered_close.callback(None)
        return self.unblock_close


def make_engine(crawler: Crawler) -> ExecutionEngine:
    """Create the engine of *crawler* as Crawler.crawl_async() (and scrapy
    shell) would, without opening or starting anything."""
    crawler.spider = crawler._create_spider()
    engine = crawler.engine = ExecutionEngine(crawler)
    return engine


async def start_engine(engine: ExecutionEngine) -> Deferred[None]:
    """Start *engine* in the background and complete once it has been started.

    Return the Deferred of the ``start_async()`` call, which completes when
    the engine is stopped.
    """
    started: Deferred[None] = Deferred()

    def handler(**kwargs: Any) -> None:
        started.callback(None)

    engine.crawler.signals.connect(handler, signals.engine_started)
    dfd = deferred_from_coro(engine.start_async())
    await maybe_deferred_to_future(started)
    engine.crawler.signals.disconnect(handler, signals.engine_started)
    return dfd


def assert_state(engine: ExecutionEngine, state: EngineState) -> None:
    assert engine.state is state, engine.state


def assert_no_invalid_transition(caplog: pytest.LogCaptureFixture) -> None:
    assert not [
        r for r in caplog.records if "Invalid engine state transition" in r.message
    ]


NORMAL_SIGNAL_ORDER = [
    "spider_opened",
    "engine_started",
    "spider_closed",
    "engine_stopped",
]
NEVER_STARTED_SIGNAL_ORDER = ["spider_opened", "spider_closed"]


class TestNormalLifecycle:
    @coroutine_test
    async def test_state_progression(self, caplog: pytest.LogCaptureFixture) -> None:
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)
        with caplog.at_level(logging.WARNING, logger="scrapy.core.engine"):
            await crawler.crawl_async()
        assert_no_invalid_transition(caplog)
        engine = crawler.engine
        assert engine is not None
        assert_state(engine, EngineState.STOPPED)
        assert not engine.running
        assert not crawler.crawling
        assert recorder.names == NORMAL_SIGNAL_ORDER
        assert recorder.states == [
            EngineState.SPIDER_OPENING,
            EngineState.STARTING,
            EngineState.SPIDER_CLOSING,
            EngineState.STOPPING,
        ]
        assert crawler.stats
        assert crawler.stats.get_value("finish_reason") == "finished"

    @coroutine_test
    async def test_stop_idempotent(self) -> None:
        crawler = get_crawler(DefaultSpider)
        await crawler.crawl_async()
        engine = crawler.engine
        assert engine is not None
        assert_state(engine, EngineState.STOPPED)
        # None of these raises or hangs on a stopped engine.
        await engine.stop_async()
        await engine.close_async()
        await engine.close_spider_async()
        assert_state(engine, EngineState.STOPPED)


class TestFetchOnlyLifecycle:
    """The lifecycle used by scrapy shell: the spider is opened, requests are
    downloaded, and the engine is never started."""

    @coroutine_test
    async def test_open_download_close(self, caplog: pytest.LogCaptureFixture) -> None:
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)
        engine = make_engine(crawler)
        assert_state(engine, EngineState.CREATED)
        with caplog.at_level(logging.WARNING, logger="scrapy.core.engine"):
            await engine.open_spider_async(close_if_idle=False)
            assert_state(engine, EngineState.SPIDER_OPEN)
            assert not engine.running
            response = await engine.download_async(Request("data:,"))
            assert response.status == 200
            # Downloads schedule the slot's next call, which must not start
            # request processing or close the idle spider.
            assert_state(engine, EngineState.SPIDER_OPEN)
            await engine.close_async()
        assert_state(engine, EngineState.STOPPED)
        assert_no_invalid_transition(caplog)
        # The engine was never started, so no engine signals are sent.
        assert recorder.names == NEVER_STARTED_SIGNAL_ORDER
        assert recorder.close_reasons == ["shutdown"]


class TestEarlyClose:
    """Closes and stops requested before or while the engine starts."""

    @coroutine_test
    async def test_close_from_engine_started_handler(self) -> None:
        """A close triggered by an engine_started handler must leave the engine
        cleanly stopped instead of half-initialized."""
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)

        async def stop(**kwargs: Any) -> None:
            await crawler.stop_async()

        crawler.signals.connect(stop, signals.engine_started)
        await crawler.crawl_async()
        engine = crawler.engine
        assert engine is not None
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NORMAL_SIGNAL_ORDER
        assert recorder.states[2] is EngineState.SPIDER_CLOSING
        assert recorder.close_reasons == ["shutdown"]

    @coroutine_test
    async def test_close_during_engine_started_handler(self) -> None:
        """If the spider is closed while an engine_started handler is still
        running, engine_stopped is sent only after that handler finishes."""
        crawler = get_crawler(DefaultSpider)
        events: list[str] = []

        async def engine_started(**kwargs: Any) -> None:
            assert crawler.engine is not None
            await crawler.engine.close_spider_async(reason="early")
            assert_state(crawler.engine, EngineState.STOPPING)
            events.append("engine_started handler finished")

        def engine_stopped(**kwargs: Any) -> None:
            events.append("engine_stopped")

        crawler.signals.connect(engine_started, signals.engine_started)
        crawler.signals.connect(engine_stopped, signals.engine_stopped)
        await crawler.crawl_async()
        assert crawler.engine is not None
        assert_state(crawler.engine, EngineState.STOPPED)
        assert events == ["engine_started handler finished", "engine_stopped"]

    @coroutine_test
    async def test_close_spider_before_start(self) -> None:
        """A spider close that completes before start_async() (e.g. triggered
        by the CloseSpider or MemoryUsage extensions) stops the never-started
        engine right away."""
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)
        engine = make_engine(crawler)
        await engine.open_spider_async()
        await engine.close_spider_async(reason="early")
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NEVER_STARTED_SIGNAL_ORDER
        assert recorder.close_reasons == ["early"]
        with pytest.raises(RuntimeError, match="in the STOPPED state"):
            await engine.start_async()

    @coroutine_test
    async def test_crawl_with_close_before_start(self) -> None:
        """Crawler.crawl_async() does not start an engine whose spider was
        closed while opening, and completes without hanging."""
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)

        async def close(**kwargs: Any) -> None:
            assert crawler.engine is not None
            await crawler.engine.close_spider_async(reason="early")

        crawler.signals.connect(close, signals.spider_opened)
        await crawler.crawl_async()
        engine = crawler.engine
        assert engine is not None
        assert_state(engine, EngineState.STOPPED)
        assert not crawler.crawling
        assert recorder.names == NEVER_STARTED_SIGNAL_ORDER
        assert recorder.close_reasons == ["early"]

    @coroutine_test
    async def test_close_in_progress_at_start(self) -> None:
        """A spider close that is still in progress when start_async() resumes
        after the engine_started signal (e.g. one scheduled by the CloseSpider
        extension while an engine_started handler was running) must not make
        start_async(), and therefore Crawler.crawl_async(), complete before
        the engine is stopped."""
        crawler = get_crawler(
            DefaultSpider, settings_dict={"SCHEDULER": BlockingScheduler}
        )
        recorder = SignalRecorder(crawler)
        close_in_progress: Deferred[None] = Deferred()
        crawl_done_at_engine_stopped: list[bool] = []
        schedulers: list[BlockingScheduler] = []

        async def engine_started(**kwargs: Any) -> None:
            engine = crawler.engine
            assert engine is not None
            scheduler = engine.scheduler
            assert isinstance(scheduler, BlockingScheduler)
            schedulers.append(scheduler)
            _schedule_coro(engine.close_spider_async(reason="early"))
            # Return once the close is under way, blocked in the scheduler.
            await maybe_deferred_to_future(scheduler.entered_close)
            close_in_progress.callback(None)

        def engine_stopped(**kwargs: Any) -> None:
            crawl_done_at_engine_stopped.append(crawl_dfd.called)

        crawler.signals.connect(engine_started, signals.engine_started)
        crawler.signals.connect(engine_stopped, signals.engine_stopped)
        crawl_dfd = deferred_from_coro(crawler.crawl_async())
        await maybe_deferred_to_future(close_in_progress)
        engine = crawler.engine
        assert engine is not None
        assert_state(engine, EngineState.SPIDER_CLOSING)
        assert not crawl_dfd.called

        schedulers[0].unblock_close.callback(None)
        await maybe_deferred_to_future(crawl_dfd)
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NORMAL_SIGNAL_ORDER
        assert recorder.close_reasons == ["early"]
        # The crawl completed only after the engine was stopped.
        assert crawl_done_at_engine_stopped == [False]

    @pytest.mark.parametrize("mode", ["graceful", "fast"])
    @coroutine_test
    async def test_crawler_stop_before_start(self, mode: _StopMode) -> None:
        """Crawler.stop_async() before the engine is started (e.g. from a
        spider_opened handler, or on Ctrl-C during a slow spider open) closes
        the spider as soon as it is open, and the crawl neither runs nor
        hangs."""
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)

        async def stop(**kwargs: Any) -> None:
            await crawler.stop_async(mode=mode)

        crawler.signals.connect(stop, signals.spider_opened)
        await crawler.crawl_async()
        engine = crawler.engine
        assert engine is not None
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NEVER_STARTED_SIGNAL_ORDER
        assert recorder.close_reasons == ["shutdown"]

    @pytest.mark.parametrize("mode", ["graceful", "fast"])
    @coroutine_test
    async def test_crawler_stop_with_open_spider(self, mode: _StopMode) -> None:
        """Crawler.stop_async() with an open spider and a never-started
        engine closes the spider and stops the engine."""
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)
        engine = make_engine(crawler)
        crawler.crawling = True  # as crawl_async() would set
        await engine.open_spider_async()
        await crawler.stop_async(mode=mode)
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NEVER_STARTED_SIGNAL_ORDER
        assert recorder.close_reasons == ["shutdown"]


class TestCloseDuringOpen:
    @coroutine_test
    async def test_close_spider_during_open(self) -> None:
        """A close requested while the spider is opening is deferred until
        the open finishes, keeping the spider_opened/spider_closed order."""
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)
        engine = make_engine(crawler)
        state_after_close_call: list[EngineState] = []

        async def close(**kwargs: Any) -> None:
            await engine.close_spider_async(reason="early")
            # The first reason wins, as for any other double close.
            await engine.close_spider_async(reason="later")
            state_after_close_call.append(engine.state)

        crawler.signals.connect(close, signals.spider_opened)
        await engine.open_spider_async()
        # The close was deferred, not performed inline in the handler.
        assert state_after_close_call == [EngineState.SPIDER_OPENING]
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NEVER_STARTED_SIGNAL_ORDER
        assert recorder.close_reasons == ["early"]

    @coroutine_test
    async def test_close_spider_during_open_with_error(self) -> None:
        """A close requested while the spider is opening keeps its error
        flag."""
        crawler = get_crawler(DefaultSpider)
        engine = make_engine(crawler)
        errors: list[bool] = []

        async def close(**kwargs: Any) -> None:
            await engine.close_spider_async(reason="early", error=True)

        def closed(error: bool, **kwargs: Any) -> None:
            errors.append(error)

        crawler.signals.connect(close, signals.spider_opened)
        crawler.signals.connect(closed, signals.spider_closed)
        await engine.open_spider_async()
        assert_state(engine, EngineState.STOPPED)
        assert errors == [True]

    @coroutine_test
    async def test_stop_during_open(self) -> None:
        """stop_async() while the spider is opening is performed once the
        spider is open."""
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)
        engine = make_engine(crawler)

        async def stop(**kwargs: Any) -> None:
            await engine.stop_async()

        crawler.signals.connect(stop, signals.spider_opened)
        await engine.open_spider_async()
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NEVER_STARTED_SIGNAL_ORDER
        assert recorder.close_reasons == ["shutdown"]

    @coroutine_test
    async def test_close_engine_during_open(self) -> None:
        """close_async() while the spider is opening defers the spider close
        and uses its own reason for it."""
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)
        engine = make_engine(crawler)

        async def close(**kwargs: Any) -> None:
            await engine.close_async(reason="early")

        crawler.signals.connect(close, signals.spider_opened)
        await engine.open_spider_async()
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NEVER_STARTED_SIGNAL_ORDER
        assert recorder.close_reasons == ["early"]


class TestDoubleClose:
    @coroutine_test
    async def test_close_after_close(self) -> None:
        """close_spider_async() after the spider has been closed returns
        instead of raising RuntimeError."""
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)
        engine = make_engine(crawler)
        await engine.open_spider_async()
        await engine.close_spider_async(reason="first")
        assert_state(engine, EngineState.STOPPED)
        await engine.close_spider_async(reason="second")
        assert recorder.close_reasons == ["first"]

    @coroutine_test
    async def test_close_while_closing(self) -> None:
        """A concurrent close_spider_async() returns instead of raising or
        starting a second close sequence."""
        crawler = get_crawler(
            DefaultSpider, settings_dict={"SCHEDULER": BlockingScheduler}
        )
        recorder = SignalRecorder(crawler)
        engine = make_engine(crawler)
        await engine.open_spider_async()
        assert engine._slot is not None
        scheduler = engine._slot.scheduler
        assert isinstance(scheduler, BlockingScheduler)

        first = deferred_from_coro(engine.close_spider_async(reason="first"))
        # Wait until the first close is underway, blocked on scheduler close.
        await maybe_deferred_to_future(scheduler.entered_close)
        assert_state(engine, EngineState.SPIDER_CLOSING)

        await engine.close_spider_async(reason="second")
        assert_state(engine, EngineState.SPIDER_CLOSING)  # still the first close

        scheduler.unblock_close.callback(None)
        await maybe_deferred_to_future(first)
        assert_state(engine, EngineState.STOPPED)
        assert recorder.close_reasons == ["first"]

    @coroutine_test
    async def test_stop_while_closing(self) -> None:
        """A stop requested while the spider is closing does not wait for the
        close, and the close finishes the stop, so that engine_stopped is
        still sent after spider_closed."""
        crawler = get_crawler(
            DefaultSpider, settings_dict={"SCHEDULER": BlockingScheduler}
        )
        recorder = SignalRecorder(crawler)
        engine = make_engine(crawler)
        await engine.open_spider_async(close_if_idle=False)
        start_dfd = await start_engine(engine)
        assert engine._slot is not None
        scheduler = engine._slot.scheduler
        assert isinstance(scheduler, BlockingScheduler)

        close_dfd = deferred_from_coro(engine.close_spider_async(reason="first"))
        await maybe_deferred_to_future(scheduler.entered_close)
        assert_state(engine, EngineState.SPIDER_CLOSING)

        await engine.stop_async()  # returns without waiting for the close
        assert_state(engine, EngineState.SPIDER_CLOSING)
        assert "engine_stopped" not in recorder.names
        assert not start_dfd.called

        scheduler.unblock_close.callback(None)
        await maybe_deferred_to_future(close_dfd)
        await maybe_deferred_to_future(start_dfd)
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NORMAL_SIGNAL_ORDER
        assert recorder.close_reasons == ["first"]

    @coroutine_test
    async def test_stop_from_spider_closed_handler(self) -> None:
        """Stopping the crawler from a spider_closed handler, i.e. from code
        that the close sequence awaits, must not deadlock."""
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)

        async def stop(**kwargs: Any) -> None:
            await crawler.stop_async()

        crawler.signals.connect(stop, signals.spider_closed)
        await crawler.crawl_async()
        engine = crawler.engine
        assert engine is not None
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NORMAL_SIGNAL_ORDER

    @coroutine_test
    async def test_stop_from_engine_stopped_handler(self) -> None:
        """Stopping the crawler from an engine_stopped handler must not
        deadlock either."""
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)

        async def stop(**kwargs: Any) -> None:
            await crawler.stop_async()

        crawler.signals.connect(stop, signals.engine_stopped)
        await crawler.crawl_async()
        engine = crawler.engine
        assert engine is not None
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NORMAL_SIGNAL_ORDER


class TestInvalidTransitions:
    """Calls that the state does not allow raise instead of transitioning, and
    a transition that the transition table does not allow is logged."""

    @coroutine_test
    async def test_transition_not_in_table_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(get_crawler(DefaultSpider))
        with caplog.at_level(logging.WARNING, logger="scrapy.core.engine"):
            engine._transition_to(EngineState.RUNNING)
        assert "Invalid engine state transition: CREATED → RUNNING" in caplog.text
        assert_state(engine, EngineState.RUNNING)
        engine.downloader.close()

    @coroutine_test
    async def test_stop_not_opened(self) -> None:
        crawler = get_crawler(DefaultSpider)
        engine = ExecutionEngine(crawler)
        with pytest.raises(RuntimeError, match="Spider not opened"):
            await engine.stop_async()
        engine.downloader.close()

    @coroutine_test
    async def test_double_open(self) -> None:
        crawler = get_crawler(DefaultSpider)
        engine = make_engine(crawler)
        await engine.open_spider_async()
        with pytest.raises(RuntimeError, match="No free spider slot"):
            await engine.open_spider_async()
        await engine.close_spider_async()

    @coroutine_test
    async def test_open_after_stop(self) -> None:
        crawler = get_crawler(DefaultSpider)
        engine = make_engine(crawler)
        await engine.close_async()
        assert_state(engine, EngineState.STOPPED)
        with pytest.raises(RuntimeError, match="engine has already been stopped"):
            await engine.open_spider_async()

    @coroutine_test
    async def test_start_after_stop(self) -> None:
        crawler = get_crawler(DefaultSpider)
        engine = make_engine(crawler)
        await engine.open_spider_async()
        await engine.close_async()
        with pytest.raises(RuntimeError, match="in the STOPPED state"):
            await engine.start_async()

    @pytest.mark.parametrize(
        ("signal", "message"),
        [
            (
                signals.spider_opened,
                "Cannot start the engine in the SPIDER_OPENING state",
            ),
            (
                signals.spider_closed,
                "Cannot start the engine in the SPIDER_CLOSING state",
            ),
        ],
    )
    @coroutine_test
    async def test_start_while_opening_or_closing(
        self, signal: object, message: str
    ) -> None:
        crawler = get_crawler(DefaultSpider)
        engine = make_engine(crawler)
        errors: list[str] = []

        async def start(**kwargs: Any) -> None:
            try:
                await engine.start_async()
            except RuntimeError as exc:
                errors.append(str(exc))

        crawler.signals.connect(start, signal)
        await engine.open_spider_async()
        await engine.close_spider_async()
        assert errors == [message]

    @coroutine_test
    async def test_close_spider_never_opened(self) -> None:
        crawler = get_crawler(DefaultSpider)
        engine = ExecutionEngine(crawler)
        with pytest.raises(RuntimeError, match="Spider not opened"):
            await engine.close_spider_async()
        engine.downloader.close()


class TestCloseAsync:
    """close_async() must work, and clean everything up, in every state."""

    @coroutine_test
    async def test_created(self) -> None:
        crawler = get_crawler(DefaultSpider)
        engine = ExecutionEngine(crawler)
        engine.downloader.close = Mock(wraps=engine.downloader.close)  # type: ignore[method-assign]
        await engine.close_async()
        assert_state(engine, EngineState.STOPPED)
        engine.downloader.close.assert_called()

    @coroutine_test
    async def test_open(self) -> None:
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)
        engine = make_engine(crawler)
        await engine.open_spider_async()
        await engine.close_async()
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NEVER_STARTED_SIGNAL_ORDER
        assert recorder.close_reasons == ["shutdown"]

    @coroutine_test
    async def test_closing(self) -> None:
        """close_async() while the spider is closing leaves the cleanup to
        that close instead of waiting for it."""
        crawler = get_crawler(
            DefaultSpider, settings_dict={"SCHEDULER": BlockingScheduler}
        )
        recorder = SignalRecorder(crawler)
        engine = make_engine(crawler)
        await engine.open_spider_async()
        assert engine._slot is not None
        scheduler = engine._slot.scheduler
        assert isinstance(scheduler, BlockingScheduler)

        close_dfd = deferred_from_coro(engine.close_spider_async(reason="first"))
        await maybe_deferred_to_future(scheduler.entered_close)
        await engine.close_async()
        assert_state(engine, EngineState.SPIDER_CLOSING)

        scheduler.unblock_close.callback(None)
        await maybe_deferred_to_future(close_dfd)
        assert_state(engine, EngineState.STOPPED)
        assert recorder.close_reasons == ["first"]

    @coroutine_test
    async def test_running(self) -> None:
        crawler = get_crawler(DefaultSpider)
        recorder = SignalRecorder(crawler)
        engine = make_engine(crawler)
        await engine.open_spider_async(close_if_idle=False)
        start_dfd = await start_engine(engine)
        await engine.close_async(reason="early")
        assert_state(engine, EngineState.STOPPED)
        assert recorder.names == NORMAL_SIGNAL_ORDER
        assert recorder.close_reasons == ["early"]
        await maybe_deferred_to_future(start_dfd)


class TestDeprecated:
    @coroutine_test
    async def test_running_setter(self) -> None:
        crawler = get_crawler(DefaultSpider)
        engine = ExecutionEngine(crawler)
        with pytest.warns(
            ScrapyDeprecationWarning,
            match="Setting ExecutionEngine.running is deprecated",
        ):
            engine.running = True
        assert engine.running is False  # setting it has no effect
        engine.downloader.close()

    @coroutine_test
    async def test_spider_closed_callback(self) -> None:
        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        callback = Mock()
        with pytest.warns(ScrapyDeprecationWarning, match="spider_closed_callback"):
            engine = crawler.engine = ExecutionEngine(crawler, callback)
        await engine.open_spider_async()
        await engine.close_spider_async()
        callback.assert_called_once_with(crawler.spider)
