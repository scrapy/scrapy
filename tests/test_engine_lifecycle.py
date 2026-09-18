from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest

from scrapy import Request, signals
from scrapy.core.engine import ExecutionEngine, _EngineState
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import Callable

    from scrapy.crawler import Crawler


class SignalRecorder:
    """Record lifecycle signals and the engine state at the time each signal
    fired."""

    SIGNALS = ("engine_started", "engine_stopped", "spider_opened", "spider_closed")

    def __init__(self, crawler: Crawler) -> None:
        self.crawler = crawler
        self.calls: list[tuple[str, _EngineState]] = []
        # Keep strong references to the handlers: signal connections are weak.
        self._handlers = [self._make_handler(name) for name in self.SIGNALS]
        for name, handler in zip(self.SIGNALS, self._handlers, strict=True):
            crawler.signals.connect(handler, getattr(signals, name))

    def _make_handler(self, name: str) -> Callable[..., None]:
        def handler(**kwargs: Any) -> None:
            assert self.crawler.engine is not None
            self.calls.append((name, self.crawler.engine._state))

        return handler

    @property
    def names(self) -> list[str]:
        return [call[0] for call in self.calls]

    @property
    def states(self) -> list[_EngineState]:
        return [call[1] for call in self.calls]


def assert_state(engine: ExecutionEngine, state: _EngineState) -> None:
    assert engine._state is state


def make_engine(crawler: Crawler) -> ExecutionEngine:
    """Create the engine of *crawler* as Crawler.crawl_async() (and scrapy
    shell) would, without opening or starting anything."""
    crawler.spider = crawler._create_spider()
    engine = crawler.engine = crawler._create_engine()
    return engine


def assert_no_invalid_transition(caplog: pytest.LogCaptureFixture) -> None:
    assert not [
        r for r in caplog.records if "Invalid engine state transition" in r.message
    ]


@coroutine_test
async def test_state_progression(caplog: pytest.LogCaptureFixture) -> None:
    crawler = get_crawler(DefaultSpider)
    recorder = SignalRecorder(crawler)
    with caplog.at_level(logging.WARNING, logger="scrapy.core.engine"):
        await crawler.crawl_async()
    assert_no_invalid_transition(caplog)
    engine = crawler.engine
    assert engine is not None
    assert_state(engine, _EngineState.STOPPED)
    assert not engine.running
    assert recorder.names == [
        "spider_opened",
        "engine_started",
        "spider_closed",
        "engine_stopped",
    ]
    assert recorder.states == [
        _EngineState.SPIDER_OPENING,
        _EngineState.STARTING,
        _EngineState.RUNNING,
        _EngineState.STOPPING,
    ]


@coroutine_test
async def test_fetch_only_lifecycle(caplog: pytest.LogCaptureFixture) -> None:
    """The lifecycle used by scrapy shell: the spider is opened, requests are
    downloaded, and the engine is never started."""
    crawler = get_crawler(DefaultSpider)
    recorder = SignalRecorder(crawler)
    engine = make_engine(crawler)
    assert_state(engine, _EngineState.CREATED)
    with caplog.at_level(logging.WARNING, logger="scrapy.core.engine"):
        await engine.open_spider_async(close_if_idle=False)
        assert_state(engine, _EngineState.SPIDER_OPEN)
        assert not engine.running
        response = await engine.download_async(Request("data:,"))
        assert response.status == 200
        assert_state(engine, _EngineState.SPIDER_OPEN)
        await engine.close_async()
    assert_state(engine, _EngineState.STOPPED)
    assert_no_invalid_transition(caplog)
    assert recorder.names == ["spider_opened", "spider_closed"]


@coroutine_test
async def test_close_created() -> None:
    engine = ExecutionEngine(get_crawler(DefaultSpider), lambda _: None)
    engine.downloader.close = Mock(wraps=engine.downloader.close)  # type: ignore[method-assign]
    await engine.close_async()
    assert_state(engine, _EngineState.STOPPED)
    engine.downloader.close.assert_called()


@coroutine_test
async def test_running_setter_deprecated() -> None:
    engine = ExecutionEngine(get_crawler(DefaultSpider), lambda _: None)
    with pytest.warns(
        ScrapyDeprecationWarning,
        match="Setting ExecutionEngine.running is deprecated",
    ):
        engine.running = True
    assert engine.running is False  # setting it has no effect
    engine.downloader.close()
