from __future__ import annotations

import asyncio
import random
import socket
import warnings
from asyncio import Future
from typing import TYPE_CHECKING, Any

import pytest
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.interfaces import IReadDescriptor
from zope.interface import implementer

from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen
from scrapy.utils.asyncio import is_asyncio_available
from scrapy.utils.defer import (
    _process_pending_io,
    aiter_errback,
    deferred_f_from_coro_f,
    deferred_from_coro,
    deferred_to_future,
    iter_errback,
    maybe_deferred_to_future,
    maybeDeferred_coro,
    mustbe_deferred,
    parallel_async,
)
from tests.utils.decorators import coroutine_test, inline_callbacks_test

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable, Generator

    from twisted.python.failure import Failure
    from typing_extensions import Self


@pytest.mark.requires_reactor  # mustbe_deferred() requires a reactor
@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestMustbeDeferred:
    @inline_callbacks_test
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

    @inline_callbacks_test
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


class TestIterErrback:
    def test_iter_errback_good(self):
        def itergood() -> Generator[int, None, None]:
            yield from range(10)

        errors: list[Failure] = []
        out = list(iter_errback(itergood(), errors.append))
        assert out == list(range(10))
        assert not errors

    def test_iter_errback_bad(self):
        def iterbad() -> Generator[int, None, None]:
            for x in range(10):
                if x == 5:
                    1 / 0
                yield x

        errors: list[Failure] = []
        out = list(iter_errback(iterbad(), errors.append))
        assert out == [0, 1, 2, 3, 4]
        assert len(errors) == 1
        assert isinstance(errors[0].value, ZeroDivisionError)


class TestAiterErrback:
    @coroutine_test
    async def test_aiter_errback_good(self):
        async def itergood() -> AsyncGenerator[int, None]:
            for x in range(10):
                yield x

        errors: list[Failure] = []
        out = await collect_asyncgen(aiter_errback(itergood(), errors.append))
        assert out == list(range(10))
        assert not errors

    @coroutine_test
    async def test_iter_errback_bad(self):
        async def iterbad() -> AsyncGenerator[int, None]:
            for x in range(10):
                if x == 5:
                    1 / 0
                yield x

        errors: list[Failure] = []
        out = await collect_asyncgen(aiter_errback(iterbad(), errors.append))
        assert out == [0, 1, 2, 3, 4]
        assert len(errors) == 1
        assert isinstance(errors[0].value, ZeroDivisionError)


class TestAsyncDefTestsuite:
    @coroutine_test
    async def test_coroutine_test(self):
        pass

    @pytest.mark.xfail(reason="Checks that the test is actually executed", strict=True)
    @coroutine_test
    async def test_coroutine_test_xfail(self):
        raise RuntimeError("This is expected to be raised")


@implementer(IReadDescriptor)
class _ReadTracker:
    """Socket that the event loop finds readable, counting how often it reads it.

    Entering the context manager registers the socket and makes it readable,
    from the next poll of the event loop on, so that a non-zero *reads* means
    that the loop has polled its file descriptors since then. *on_read*, if
    given, is called on every read.
    """

    def __init__(self, on_read: Callable[[], None] | None = None) -> None:
        self._on_read = on_read
        self._rx, self._tx = socket.socketpair()
        self.reads = 0

    def _read(self) -> None:
        self.reads += 1
        self._rx.recv(1)
        if self._on_read is not None:
            self._on_read()

    def fileno(self) -> int:
        return self._rx.fileno()

    doRead = _read

    def connectionLost(self, reason: Failure) -> None:
        pass

    def logPrefix(self) -> str:
        return "read-tracker"

    def __enter__(self) -> Self:
        if is_asyncio_available():
            asyncio.get_event_loop().add_reader(self._rx, self._read)
        else:
            from twisted.internet import reactor

            reactor.addReader(self)
        self._tx.send(b"x")
        return self

    def __exit__(self, *exc_info: object) -> None:
        if is_asyncio_available():
            asyncio.get_event_loop().remove_reader(self._rx)
        else:
            from twisted.internet import reactor

            reactor.removeReader(self)
        self._rx.close()
        self._tx.close()


@coroutine_test
async def test_process_pending_io() -> None:
    # The wait runs from a read callback, which is where Scrapy's own waits
    # happen, since what precedes them is a response arriving over a socket. It
    # is also the strictest place to wait from: the event loop polled right
    # before calling us, so only another poll can read the socket that check()
    # registers.
    done: Deferred[int] = Deferred()

    async def check() -> None:
        with _ReadTracker() as tracker:
            await _process_pending_io()
            done.callback(tracker.reads)

    def start() -> None:
        deferred_from_coro(check()).addErrback(done.errback)

    with _ReadTracker(on_read=start):
        reads = await maybe_deferred_to_future(done)
    assert reads


@pytest.mark.requires_reactor  # parallel_async() requires a reactor
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

    @inline_callbacks_test
    def test_simple(self):
        for length in [20, 50, 100]:
            parallel_count = [0]
            max_parallel_count = [0]
            results: list[int] = []
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

    @inline_callbacks_test
    def test_delays(self):
        for length in [20, 50, 100]:
            parallel_count = [0]
            max_parallel_count = [0]
            results: list[int] = []
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
        d: Deferred[None] = Deferred()
        result = deferred_from_coro(d)
        assert isinstance(result, Deferred)
        assert result is d

    def test_object(self):
        result = deferred_from_coro(42)
        assert result == 42

    @inline_callbacks_test
    def test_coroutine(self):
        async def coroutine() -> int:
            return 42

        result = deferred_from_coro(coroutine())
        assert isinstance(result, Deferred)
        coro_result = yield result
        assert coro_result == 42

    @pytest.mark.only_asyncio
    @inline_callbacks_test
    def test_coroutine_asyncio(self):
        async def coroutine() -> int:
            await asyncio.sleep(0.01)
            return 42

        result = deferred_from_coro(coroutine())
        assert isinstance(result, Deferred)
        coro_result = yield result
        assert coro_result == 42

    @pytest.mark.only_asyncio
    @inline_callbacks_test
    def test_future(self):
        future: Future[int] = Future()
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

    @inline_callbacks_test
    def test_coroutine(self):
        async def c_f() -> int:
            return 42

        yield self._assert_result(c_f)

    @pytest.mark.only_asyncio
    @inline_callbacks_test
    def test_coroutine_asyncio(self):
        async def c_f() -> int:
            await asyncio.sleep(0.01)
            return 42

        yield self._assert_result(c_f)

    @pytest.mark.only_asyncio
    @inline_callbacks_test
    def test_future(self):
        def c_f() -> Future[int]:
            f: Future[int] = Future()
            f.set_result(42)
            return f

        yield self._assert_result(c_f)


@pytest.mark.only_asyncio
class TestDeferredToFuture:
    @coroutine_test
    async def test_deferred(self):
        d: Deferred[int] = Deferred()
        result = deferred_to_future(d)
        assert isinstance(result, Future)
        d.callback(42)
        future_result = await result
        assert future_result == 42

    @coroutine_test
    async def test_wrapped_coroutine(self):
        async def c_f() -> int:
            return 42

        d = deferred_from_coro(c_f())
        result = deferred_to_future(d)
        assert isinstance(result, Future)
        future_result = await result
        assert future_result == 42

    @coroutine_test
    async def test_wrapped_coroutine_asyncio(self):
        async def c_f() -> int:
            await asyncio.sleep(0.01)
            return 42

        d = deferred_from_coro(c_f())
        result = deferred_to_future(d)
        assert isinstance(result, Future)
        future_result = await result
        assert future_result == 42


@pytest.mark.only_not_asyncio
class TestDeferredToFutureNotAsyncio:
    def test_deferred(self):
        with pytest.raises(
            RuntimeError, match=r"deferred_to_future\(\) requires an installed asyncio"
        ):
            deferred_to_future(Deferred())


@pytest.mark.only_asyncio
class TestMaybeDeferredToFutureAsyncio:
    @coroutine_test
    async def test_deferred(self):
        d: Deferred[int] = Deferred()
        result = maybe_deferred_to_future(d)
        assert isinstance(result, Future)
        d.callback(42)
        future_result = await result
        assert future_result == 42

    @coroutine_test
    async def test_wrapped_coroutine(self):
        async def c_f() -> int:
            return 42

        d = deferred_from_coro(c_f())
        result = maybe_deferred_to_future(d)
        assert isinstance(result, Future)
        future_result = await result
        assert future_result == 42

    @coroutine_test
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
    @coroutine_test
    async def test_deferred(self):
        d: Deferred[int] = Deferred()
        result = maybe_deferred_to_future(d)
        assert isinstance(result, Deferred)
        assert result is d


def test_maybe_deferred_coro_deferred() -> None:
    d: Deferred[int] = Deferred()
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        assert maybeDeferred_coro(lambda: d) is d
    # Only the deprecation of maybeDeferred_coro() itself is reported; callables
    # that return a Deferred are the reason it exists.
    assert [str(record.message) for record in records] == [
        "maybeDeferred_coro() is deprecated and will be removed in a future"
        " Scrapy version."
    ]
