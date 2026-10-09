from __future__ import annotations

import asyncio
import random
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from twisted.internet.defer import Deferred

import scrapy.utils.asyncio
from scrapy.utils.asyncgen import as_async_generator
from scrapy.utils.asyncio import (
    AsyncioLoopingCall,
    _parallel_asyncio,
    call_later,
    is_asyncio_available,
    sleep,
)
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Iterator


@coroutine_test
async def test_is_asyncio_available(reactor_pytest: str) -> None:
    # the result should depend only on the pytest --reactor argument
    assert is_asyncio_available() == (reactor_pytest != "default")


@coroutine_test
async def test_sleep() -> None:
    events: list[str] = []
    call_later(0.05, events.append, "call_later")
    await sleep(0.1)
    events.append("sleep")
    assert events == ["call_later", "sleep"]


@pytest.mark.only_asyncio
class TestParallelAsyncio:
    """Test for scrapy.utils.asyncio.parallel_asyncio(), based on tests.test_utils_defer.TestParallelAsync."""

    CONCURRENT_ITEMS = 50

    @staticmethod
    async def callable(o: int, results: list[int]) -> None:
        if random.random() < 0.4:
            # simulate async processing
            await asyncio.sleep(random.random() / 8)
        # simulate trivial sync processing
        results.append(o)

    async def callable_wrapped(
        self,
        o: int,
        results: list[int],
        parallel_count: list[int],
        max_parallel_count: list[int],
    ) -> None:
        parallel_count[0] += 1
        max_parallel_count[0] = max(max_parallel_count[0], parallel_count[0])
        await self.callable(o, results)
        assert parallel_count[0] > 0, parallel_count[0]
        parallel_count[0] -= 1

    @staticmethod
    def get_async_iterable(length: int) -> AsyncGenerator[int, None]:
        # simulate a simple callback without delays between results
        return as_async_generator(range(length))

    @staticmethod
    async def get_async_iterable_with_delays(length: int) -> AsyncGenerator[int, None]:
        # simulate a callback with delays between some of the results
        for i in range(length):
            if random.random() < 0.1:
                await asyncio.sleep(random.random() / 20)
            yield i

    @coroutine_test
    async def test_simple(self):
        for length in [20, 50, 100]:
            parallel_count = [0]
            max_parallel_count = [0]
            results: list[int] = []
            ait = self.get_async_iterable(length)
            await _parallel_asyncio(
                ait,
                self.CONCURRENT_ITEMS,
                self.callable_wrapped,
                results,
                parallel_count,
                max_parallel_count,
            )
            assert list(range(length)) == sorted(results)
            assert parallel_count[0] == 0
            assert max_parallel_count[0] <= self.CONCURRENT_ITEMS

    @coroutine_test
    async def test_delays(self):
        for length in [20, 50, 100]:
            parallel_count = [0]
            max_parallel_count = [0]
            results: list[int] = []
            ait = self.get_async_iterable_with_delays(length)
            await _parallel_asyncio(
                ait,
                self.CONCURRENT_ITEMS,
                self.callable_wrapped,
                results,
                parallel_count,
                max_parallel_count,
            )
            assert list(range(length)) == sorted(results)
            assert parallel_count[0] == 0
            assert max_parallel_count[0] <= self.CONCURRENT_ITEMS

    @coroutine_test
    async def test_count_higher_than_work(self):
        results: list[int] = []
        task_counts: list[int] = []

        async def callable_(o: int) -> None:
            task_counts.append(len(asyncio.all_tasks()))
            results.append(o)

        await _parallel_asyncio(range(3), 1_000_000, callable_)
        assert results == [0, 1, 2]
        assert max(task_counts) < 100


_real_sleep = asyncio.sleep


class _FakeTime:
    """A clock for :class:`~scrapy.utils.asyncio.AsyncioLoopingCall` that only
    advances when the looping call sleeps or when a test advances it.

    Each sleep ends *early* seconds before the requested time, like event loops
    with timers coarser than :func:`time.monotonic` can do.
    """

    def __init__(self, *, early: float = 0.0):
        self.now = 0.0
        self._early = early

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.now += max(delay - self._early, 0.0)
        await _real_sleep(0)

    @contextmanager
    def patch(self) -> Iterator[None]:
        with (
            mock.patch.object(scrapy.utils.asyncio, "time", self),
            mock.patch.object(asyncio, "sleep", self.sleep),
        ):
            yield


async def _wait_for(condition: Callable[[], bool]) -> None:
    """Let other tasks run until *condition* is met, giving up after 1000
    event loop iterations."""
    for _ in range(1000):
        if condition():
            return
        await _real_sleep(0)


@pytest.mark.only_asyncio
class TestAsyncioLoopingCall:
    @coroutine_test
    async def test_looping_call(self):
        func = mock.MagicMock()
        looping_call = AsyncioLoopingCall(func)
        looping_call.start(1, now=False)
        assert looping_call.running
        looping_call.stop()
        assert not looping_call.running
        assert not func.called

    @coroutine_test
    async def test_looping_call_now(self):
        func = mock.MagicMock()
        looping_call = AsyncioLoopingCall(func)
        looping_call.start(1)
        looping_call.stop()
        assert func.called

    @coroutine_test
    async def test_looping_call_already_running(self):
        looping_call = AsyncioLoopingCall(lambda: None)
        looping_call.start(1)
        with pytest.raises(RuntimeError):
            looping_call.start(1)
        looping_call.stop()

    @coroutine_test
    async def test_looping_call_interval(self):
        looping_call = AsyncioLoopingCall(lambda: None)
        with pytest.raises(ValueError, match="Interval must be greater than 0"):
            looping_call.start(0)
        with pytest.raises(ValueError, match="Interval must be greater than 0"):
            looping_call.start(-1)
        assert not looping_call.running

    @coroutine_test
    async def test_looping_call_bad_function(self):
        looping_call: AsyncioLoopingCall[[], Deferred[Any]] = AsyncioLoopingCall(
            Deferred
        )
        with pytest.raises(TypeError):
            looping_call.start(0.1)
        assert not looping_call.running

    @coroutine_test
    async def test_looping_function_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        looping_call = AsyncioLoopingCall(lambda: 1 / 0)
        looping_call.start(0.1)
        assert not looping_call.running
        assert "Error calling the AsyncioLoopingCall function" in caplog.text

    @coroutine_test
    async def test_looping_call_early_wakeup(self) -> None:
        """The function must be called exactly once per interval boundary even
        if the event loop wakes the looping call before time.monotonic()
        reaches the boundary (this can happen e.g. under uvloop)."""
        fake_time = _FakeTime(early=0.001)
        calls: list[float] = []
        looping_call = AsyncioLoopingCall(lambda: calls.append(fake_time.now))
        with fake_time.patch():
            looping_call.start(1, now=False)
            await _wait_for(lambda: len(calls) >= 5)
            looping_call.stop()
        assert calls == pytest.approx([0.999, 1.999, 2.999, 3.999, 4.999])

    @coroutine_test
    async def test_looping_call_late_wakeup(self) -> None:
        """If the function is late (e.g. because the event loop was blocked),
        the calls for the missed boundaries are skipped and the next call
        happens on the next boundary, not immediately."""
        fake_time = _FakeTime()
        calls: list[float] = []

        def func() -> None:
            calls.append(fake_time.now)
            if len(calls) == 1:
                fake_time.now += 2.5  # the call blocks the loop for 2.5 intervals

        looping_call = AsyncioLoopingCall(func)
        with fake_time.patch():
            looping_call.start(1, now=False)
            await _wait_for(lambda: len(calls) >= 3)
            looping_call.stop()
        assert calls == [1, 4, 5]
