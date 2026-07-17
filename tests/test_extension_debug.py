from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from scrapy.extensions.debug import Debugger, StackTraceDump
from scrapy.spiders import Spider
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def preserve_signal_handlers() -> Generator[None]:
    """Restore the signal handlers that the extensions replace."""
    signums = [
        getattr(signal, name)
        for name in ("SIGUSR2", "SIGQUIT")
        if hasattr(signal, name)
    ]
    handlers = {signum: signal.getsignal(signum) for signum in signums}
    yield
    for signum, handler in handlers.items():
        signal.signal(signum, handler)


class SignalSpider(Spider):
    name = "signal_spider"
    start_urls = ["data:,"]

    def parse(self, response):
        os.kill(os.getpid(), signal.SIGUSR2)
        return []


@pytest.mark.skipif(
    sys.platform == "win32", reason="SIGUSR2 and SIGQUIT are POSIX-only"
)
def test_stacktracedump_installs_signal_handlers() -> None:
    crawler = get_crawler()
    ext = StackTraceDump.from_crawler(crawler)
    assert signal.getsignal(signal.SIGUSR2) == ext.dump_stacktrace  # pylint: disable=comparison-with-callable
    assert signal.getsignal(signal.SIGQUIT) == ext.dump_stacktrace  # pylint: disable=comparison-with-callable


def test_stacktracedump_works_without_signal_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # simulate win32 platforms, which don't support SIGUSR signals
    monkeypatch.delattr(signal, "SIGUSR2", raising=False)
    ext = StackTraceDump.from_crawler(get_crawler())
    assert isinstance(ext, StackTraceDump)


def test_stacktracedump_dump_stacktrace(caplog: pytest.LogCaptureFixture) -> None:
    crawler = get_crawler()
    crawler.engine = mock.Mock()
    ext = StackTraceDump.from_crawler(crawler)
    spider = DefaultSpider()
    with caplog.at_level(logging.INFO, logger="scrapy.extensions.debug"):
        ext.dump_stacktrace(0, None)
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "Dumping stack trace and engine status" in message
    assert "Execution engine status" in message
    assert "Live References" in message
    assert type(spider).__name__ in message
    assert "# Thread: MainThread" in message
    assert getattr(caplog.records[0], "crawler", None) is crawler


def test_stacktracedump_thread_stacks() -> None:
    ext = StackTraceDump.from_crawler(get_crawler())
    stop = threading.Event()
    thread = threading.Thread(target=stop.wait, name="dump-test-thread")
    thread.start()
    try:
        stacks = ext._thread_stacks()
    finally:
        stop.set()
        thread.join()
    assert "# Thread: MainThread" in stacks
    assert "# Thread: dump-test-thread" in stacks


@pytest.mark.skipif(sys.platform == "win32", reason="SIGUSR2 is POSIX-only")
@coroutine_test
async def test_stacktracedump_dumps_on_signal(caplog: pytest.LogCaptureFixture) -> None:
    settings = {
        "EXTENSIONS": {"scrapy.extensions.debug.StackTraceDump": 0},
        "LOG_LEVEL": "INFO",
    }
    crawler = get_crawler(spidercls=SignalSpider, settings_dict=settings)
    with caplog.at_level(logging.INFO, logger="scrapy.extensions.debug"):
        await crawler.crawl_async()
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "Dumping stack trace and engine status" in message
    assert "engine.spider.name" in message
    assert "signal_spider" in message


@pytest.mark.skipif(sys.platform == "win32", reason="SIGUSR2 is POSIX-only")
def test_debugger_installs_signal_handler() -> None:
    ext = Debugger()
    assert signal.getsignal(signal.SIGUSR2) == ext._enter_debugger  # pylint: disable=comparison-with-callable


def test_debugger_works_without_signal_support(monkeypatch: pytest.MonkeyPatch) -> None:
    # simulate win32 platforms, which don't support SIGUSR signals
    monkeypatch.delattr(signal, "SIGUSR2", raising=False)
    ext = Debugger()
    assert isinstance(ext, Debugger)


def test_debugger_enter_debugger(monkeypatch: pytest.MonkeyPatch) -> None:
    pdb_cls = mock.Mock()
    monkeypatch.setattr("scrapy.extensions.debug.Pdb", pdb_cls)
    ext = Debugger()
    frame = sys._getframe()
    ext._enter_debugger(0, frame)
    pdb_cls.return_value.set_trace.assert_called_once_with(frame.f_back)
