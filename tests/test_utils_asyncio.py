from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING
from unittest import mock

import pytest
from twisted.internet.defer import Deferred

from scrapy.utils.asyncgen import as_async_generator
from scrapy.utils.asyncio import (
    AsyncioLoopingCall,
    _parallel_asyncio,
    is_asyncio_available,
)
from scrapy.utils.defer import deferred_f_from_coro_f

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class TestAsyncio:
    def test_is_asyncio_available(self, reactor_pytest: str) -> None:
        # the result should depend only on the pytest --reactor argument
        assert is_asyncio_available() == (reactor_pytest == "asyncio")


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

    @deferred_f_from_coro_f
    async def test_simple(self):
        for length in [20, 50, 100]:
            parallel_count = [0]
            max_parallel_count = [0]
            results = []
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
            assert max_parallel_count[0] <= self.CONCURRENT_ITEMS

    @deferred_f_from_coro_f
    async def test_delays(self):
        for length in [20, 50, 100]:
            parallel_count = [0]
            max_parallel_count = [0]
            results = []
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
            assert max_parallel_count[0] <= self.CONCURRENT_ITEMS


@pytest.mark.only_asyncio
class TestAsyncioLoopingCall:
    def test_looping_call(self):
        func = mock.MagicMock()
        looping_call = AsyncioLoopingCall(func)
        looping_call.start(1, now=False)
        assert looping_call.running
        looping_call.stop()
        assert not looping_call.running
        assert not func.called

    def test_looping_call_now(self):
        func = mock.MagicMock()
        looping_call = AsyncioLoopingCall(func)
        looping_call.start(1)
        looping_call.stop()
        assert func.called

    def test_looping_call_already_running(self):
        looping_call = AsyncioLoopingCall(lambda: None)
        looping_call.start(1)
        with pytest.raises(RuntimeError):
            looping_call.start(1)
        looping_call.stop()

    def test_looping_call_interval(self):
        looping_call = AsyncioLoopingCall(lambda: None)
        with pytest.raises(ValueError, match="Interval must be greater than 0"):
            looping_call.start(0)
        with pytest.raises(ValueError, match="Interval must be greater than 0"):
            looping_call.start(-1)
        assert not looping_call.running

    def test_looping_call_bad_function(self):
        looping_call = AsyncioLoopingCall(Deferred)
        with pytest.raises(TypeError):
            looping_call.start(0.1)
        assert not looping_call.running
