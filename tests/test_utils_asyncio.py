from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

import pytest
from twisted.trial import unittest

from scrapy.utils.asyncgen import as_async_generator
from scrapy.utils.asyncio import _parallel_asyncio, is_asyncio_available
from scrapy.utils.defer import deferred_f_from_coro_f

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.mark.usefixtures("reactor_pytest")
class TestAsyncio:
    def test_is_asyncio_available(self):
        # the result should depend only on the pytest --reactor argument
        assert is_asyncio_available() == (self.reactor_pytest != "default")


@pytest.mark.only_asyncio
class TestParallelAsyncio(unittest.TestCase):
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
