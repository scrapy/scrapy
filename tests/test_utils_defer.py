from __future__ import annotations

import asyncio
import random
from asyncio import Future
from typing import TYPE_CHECKING, Any

import pytest
from twisted.internet.defer import Deferred, inlineCallbacks, succeed
from twisted.python.failure import Failure

from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen
from scrapy.utils.defer import (
    aiter_errback,
    deferred_f_from_coro_f,
    deferred_from_coro,
    deferred_to_future,
    iter_errback,
    maybe_deferred_to_future,
    mustbe_deferred,
    parallel_async,
    process_chain,
    process_parallel,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable, Generator


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestMustbeDeferred:
    @inlineCallbacks
    def test_success_function(self) -> Generator[Deferred[Any], Any, None]:
        steps: list[int] = []

        def _append(v: int) -> list[int]:
            steps.append(v)
            return steps

        def _assert(v: list[int]) -> None:
            assert v == [1, 2]  # it is [1] with maybeDeferred

        dfd = mustbe_deferred(_append, 1)
        dfd.addCallback(_assert)
        steps.append(2)  # add another value, that should be caught by assertEqual
        yield dfd

    @inlineCallbacks
    def test_unfired_deferred(self) -> Generator[Deferred[Any], Any, None]:
        steps: list[int] = []

        def _append(v: int) -> Deferred[list[int]]:
            from twisted.internet import reactor

            steps.append(v)
            dfd: Deferred[list[int]] = Deferred()
            reactor.callLater(0, dfd.callback, steps)
            return dfd

        def _assert(v: list[int]) -> None:
            assert v == [1, 2]

        dfd = mustbe_deferred(_append, 1)
        dfd.addCallback(_assert)
        steps.append(2)  # add another value, that should be caught by assertEqual
        yield dfd


def cb1(value, arg1, arg2):
    return f"(cb1 {value} {arg1} {arg2})"


def cb2(value, arg1, arg2):
    return succeed(f"(cb2 {value} {arg1} {arg2})")


def cb3(value, arg1, arg2):
    return f"(cb3 {value} {arg1} {arg2})"


def cb_fail(value, arg1, arg2):
    return Failure(TypeError())


def eb1(failure, arg1, arg2):
    return f"(eb1 {failure.value.__class__.__name__} {arg1} {arg2})"


class TestDeferUtils:
    @inlineCallbacks
    def test_process_chain(self):
        x = yield process_chain([cb1, cb2, cb3], "res", "v1", "v2")
        assert x == "(cb3 (cb2 (cb1 res v1 v2) v1 v2) v1 v2)"

        with pytest.raises(TypeError):
            yield process_chain([cb1, cb_fail, cb3], "res", "v1", "v2")

    @inlineCallbacks
    def test_process_parallel(self):
        x = yield process_parallel([cb1, cb2, cb3], "res", "v1", "v2")
        assert x == ["(cb1 res v1 v2)", "(cb2 res v1 v2)", "(cb3 res v1 v2)"]

    @inlineCallbacks
    def test_process_parallel_failure(self):
        with pytest.raises(TypeError):
            yield process_parallel([cb1, cb_fail, cb3], "res", "v1", "v2")


class TestIterErrback:
    def test_iter_errback_good(self):
        def itergood() -> Generator[int, None, None]:
            yield from range(10)

        errors = []
        out = list(iter_errback(itergood(), errors.append))
        assert out == list(range(10))
        assert not errors

    def test_iter_errback_bad(self):
        def iterbad() -> Generator[int, None, None]:
            for x in range(10):
                if x == 5:
                    1 / 0
                yield x

        errors = []
        out = list(iter_errback(iterbad(), errors.append))
        assert out == [0, 1, 2, 3, 4]
        assert len(errors) == 1
        assert isinstance(errors[0].value, ZeroDivisionError)


class TestAiterErrback:
    @deferred_f_from_coro_f
    async def test_aiter_errback_good(self):
        async def itergood() -> AsyncGenerator[int, None]:
            for x in range(10):
                yield x

        errors = []
        out = await collect_asyncgen(aiter_errback(itergood(), errors.append))
        assert out == list(range(10))
        assert not errors

    @deferred_f_from_coro_f
    async def test_iter_errback_bad(self):
        async def iterbad() -> AsyncGenerator[int, None]:
            for x in range(10):
                if x == 5:
                    1 / 0
                yield x

        errors = []
        out = await collect_asyncgen(aiter_errback(iterbad(), errors.append))
        assert out == [0, 1, 2, 3, 4]
        assert len(errors) == 1
        assert isinstance(errors[0].value, ZeroDivisionError)


class TestAsyncDefTestsuite:
    @deferred_f_from_coro_f
    async def test_deferred_f_from_coro_f(self):
        pass

    @deferred_f_from_coro_f
    async def test_deferred_f_from_coro_f_generator(self):
        yield

    @pytest.mark.xfail(reason="Checks that the test is actually executed", strict=True)
    @deferred_f_from_coro_f
    async def test_deferred_f_from_coro_f_xfail(self):
        raise RuntimeError("This is expected to be raised")


class TestParallelAsync:
    """This tests _AsyncCooperatorAdapter by testing parallel_async which is its only usage.

    parallel_async is called with the results of a callback (so an iterable of items, requests and None,
    with arbitrary delays between values), and it uses Scraper._process_spidermw_output as the callable
    (so a callable that returns a Deferred for an item, which will fire after pipelines process it, and
    None for everything else). The concurrent task count is the CONCURRENT_ITEMS setting.

    We want to test different concurrency values compared to the iterable length.
    We also want to simulate the real usage, with arbitrary delays between getting the values
    from the iterable. We also want to simulate sync and async results from the callable.
    """

    CONCURRENT_ITEMS = 50

    @staticmethod
    def callable(o: int, results: list[int]) -> Deferred[None] | None:
        from twisted.internet import reactor

        if random.random() < 0.4:
            # simulate async processing
            dfd: Deferred[None] = Deferred()
            dfd.addCallback(lambda _: results.append(o))
            delay = random.random() / 8
            reactor.callLater(delay, dfd.callback, None)
            return dfd
        # simulate trivial sync processing
        results.append(o)
        return None

    def callable_wrapped(
        self,
        o: int,
        results: list[int],
        parallel_count: list[int],
        max_parallel_count: list[int],
    ) -> Deferred[None] | None:
        parallel_count[0] += 1
        max_parallel_count[0] = max(max_parallel_count[0], parallel_count[0])
        dfd = self.callable(o, results)

        def decrement(_: Any = None) -> None:
            assert parallel_count[0] > 0, parallel_count[0]
            parallel_count[0] -= 1

        if dfd is not None:
            dfd.addBoth(decrement)
        else:
            decrement()
        return dfd

    @staticmethod
    def get_async_iterable(length: int) -> AsyncGenerator[int, None]:
        # simulate a simple callback without delays between results
        return as_async_generator(range(length))

    @staticmethod
    async def get_async_iterable_with_delays(length: int) -> AsyncGenerator[int, None]:
        # simulate a callback with delays between some of the results
        from twisted.internet import reactor

        for i in range(length):
            if random.random() < 0.1:
                dfd: Deferred[None] = Deferred()
                delay = random.random() / 20
                reactor.callLater(delay, dfd.callback, None)
                await maybe_deferred_to_future(dfd)
            yield i

    @inlineCallbacks
    def test_simple(self):
        for length in [20, 50, 100]:
            parallel_count = [0]
            max_parallel_count = [0]
            results = []
            ait = self.get_async_iterable(length)
            dl = parallel_async(
                ait,
                self.CONCURRENT_ITEMS,
                self.callable_wrapped,
                results,
                parallel_count,
                max_parallel_count,
            )
            yield dl
            assert list(range(length)) == sorted(results)
            assert parallel_count[0] == 0
            assert max_parallel_count[0] <= self.CONCURRENT_ITEMS, max_parallel_count[0]

    @inlineCallbacks
    def test_delays(self):
        for length in [20, 50, 100]:
            parallel_count = [0]
            max_parallel_count = [0]
            results = []
            ait = self.get_async_iterable_with_delays(length)
            dl = parallel_async(
                ait,
                self.CONCURRENT_ITEMS,
                self.callable_wrapped,
                results,
                parallel_count,
                max_parallel_count,
            )
            yield dl
            assert list(range(length)) == sorted(results)
            assert parallel_count[0] == 0
            assert max_parallel_count[0] <= self.CONCURRENT_ITEMS, max_parallel_count[0]


class TestDeferredFromCoro:
    def test_deferred(self):
        d = Deferred()
        result = deferred_from_coro(d)
        assert isinstance(result, Deferred)
        assert result is d

    def test_object(self):
        result = deferred_from_coro(42)
        assert result == 42

    @inlineCallbacks
    def test_coroutine(self):
        async def coroutine() -> int:
            return 42

        result = deferred_from_coro(coroutine())
        assert isinstance(result, Deferred)
        coro_result = yield result
        assert coro_result == 42

    @pytest.mark.only_asyncio
    @inlineCallbacks
    def test_coroutine_asyncio(self):
        async def coroutine() -> int:
            await asyncio.sleep(0.01)
            return 42

        result = deferred_from_coro(coroutine())
        assert isinstance(result, Deferred)
        coro_result = yield result
        assert coro_result == 42

    @pytest.mark.only_asyncio
    @inlineCallbacks
    def test_future(self):
        future = Future()
        result = deferred_from_coro(future)
        assert isinstance(result, Deferred)
        future.set_result(42)
        future_result = yield result
        assert future_result == 42


class TestDeferredFFromCoroF:
    @inlineCallbacks
    def _assert_result(
        self, c_f: Callable[[], Awaitable[int]]
    ) -> Generator[Deferred[Any], Any, None]:
        d_f = deferred_f_from_coro_f(c_f)
        d = d_f()
        assert isinstance(d, Deferred)
        result = yield d
        assert result == 42

    @inlineCallbacks
    def test_coroutine(self):
        async def c_f() -> int:
            return 42

        yield self._assert_result(c_f)

    @inlineCallbacks
    def test_coroutine_asyncio(self):
        async def c_f() -> int:
            return 42

        yield self._assert_result(c_f)

    @pytest.mark.only_asyncio
    @inlineCallbacks
    def test_future(self):
        def c_f() -> Future[int]:
            f: Future[int] = Future()
            f.set_result(42)
            return f

        yield self._assert_result(c_f)


@pytest.mark.only_asyncio
class TestDeferredToFuture:
    @deferred_f_from_coro_f
    async def test_deferred(self):
        d = Deferred()
        result = deferred_to_future(d)
        assert isinstance(result, Future)
        d.callback(42)
        future_result = await result
        assert future_result == 42

    @deferred_f_from_coro_f
    async def test_wrapped_coroutine(self):
        async def c_f() -> int:
            return 42

        d = deferred_from_coro(c_f())
        result = deferred_to_future(d)
        assert isinstance(result, Future)
        future_result = await result
        assert future_result == 42

    @deferred_f_from_coro_f
    async def test_wrapped_coroutine_asyncio(self):
        async def c_f() -> int:
            await asyncio.sleep(0.01)
            return 42

        d = deferred_from_coro(c_f())
        result = deferred_to_future(d)
        assert isinstance(result, Future)
        future_result = await result
        assert future_result == 42


@pytest.mark.only_asyncio
class TestMaybeDeferredToFutureAsyncio:
    @deferred_f_from_coro_f
    async def test_deferred(self):
        d = Deferred()
        result = maybe_deferred_to_future(d)
        assert isinstance(result, Future)
        d.callback(42)
        future_result = await result
        assert future_result == 42

    @deferred_f_from_coro_f
    async def test_wrapped_coroutine(self):
        async def c_f() -> int:
            return 42

        d = deferred_from_coro(c_f())
        result = maybe_deferred_to_future(d)
        assert isinstance(result, Future)
        future_result = await result
        assert future_result == 42

    @deferred_f_from_coro_f
    async def test_wrapped_coroutine_asyncio(self):
        async def c_f() -> int:
            await asyncio.sleep(0.01)
            return 42

        d = deferred_from_coro(c_f())
        result = maybe_deferred_to_future(d)
        assert isinstance(result, Future)
        future_result = await result
        assert future_result == 42


@pytest.mark.only_not_asyncio
class TestMaybeDeferredToFutureNotAsyncio:
    def test_deferred(self):
        d = Deferred()
        result = maybe_deferred_to_future(d)
        assert isinstance(result, Deferred)
        assert result is d
