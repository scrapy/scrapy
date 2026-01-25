"""Utilities related to asyncio and its support in Scrapy."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Coroutine, Iterable
from typing import TYPE_CHECKING, Any, Concatenate, ParamSpec, TypeVar

from twisted.internet.defer import Deferred
from twisted.internet.task import LoopingCall

from scrapy.utils.asyncgen import as_async_generator
from scrapy.utils.reactor import is_asyncio_reactor_installed, is_reactor_installed

if TYPE_CHECKING:
    from twisted.internet.base import DelayedCall

    # typing.Self, typing.TypeVarTuple and typing.Unpack require Python 3.11
    from typing_extensions import Self, TypeVarTuple, Unpack

    _Ts = TypeVarTuple("_Ts")


_T = TypeVar("_T")
_P = ParamSpec("_P")


logger = logging.getLogger(__name__)


def is_asyncio_available() -> bool:
    """Check if it's possible to call asyncio code that relies on the asyncio event loop.

    .. versionadded:: 2.14

    Currently this function is identical to
    :func:`scrapy.utils.reactor.is_asyncio_reactor_installed`: it returns
    ``True`` if the Twisted reactor that is installed is
    :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor`, returns
    ``False`` if a different reactor is installed, and raises a
    :exc:`RuntimeError` if no reactor is installed. In a future Scrapy version,
    when Scrapy supports running without a Twisted reactor, this function will
    also return ``True`` when running in that mode, so code that doesn't
    directly require a Twisted reactor should use this function instead of
    :func:`~scrapy.utils.reactor.is_asyncio_reactor_installed`.

    When this returns ``True``, an asyncio loop is installed and used by
    Scrapy. It's possible to call functions that require it, such as
    :func:`asyncio.sleep`, and await on :class:`asyncio.Future` objects in
    Scrapy-related code.

    When this returns ``False``, a non-asyncio Twisted reactor is installed.
    It's not possible to use asyncio features that require an asyncio event
    loop or await on :class:`asyncio.Future` objects in Scrapy-related code,
    but it's possible to await on :class:`~twisted.internet.defer.Deferred`
    objects.
    """
    if not is_reactor_installed():
        raise RuntimeError(
            "is_asyncio_available() called without an installed reactor."
        )

    return is_asyncio_reactor_installed()


async def _parallel_asyncio(
    iterable: Iterable[_T] | AsyncIterator[_T],
    count: int,
    callable_: Callable[Concatenate[_T, _P], Coroutine[Any, Any, None]],
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> None:
    """Execute a callable over the objects in the given iterable, in parallel,
    using no more than ``count`` concurrent calls.

    This function is only used in
    :meth:`scrapy.core.scraper.Scraper.handle_spider_output_async` and so it
    assumes that neither *callable* nor iterating *iterable* will raise an
    exception.
    """
    queue: asyncio.Queue[_T | None] = asyncio.Queue(count * 2)

    async def worker() -> None:
        while True:
            item = await queue.get()
            if item is None:
                break
            try:
                await callable_(item, *args, **kwargs)
            finally:
                queue.task_done()

    async def fill_queue() -> None:
        async for item in as_async_generator(iterable):
            await queue.put(item)
        for _ in range(count):
            await queue.put(None)

    fill_task = asyncio.create_task(fill_queue())
    work_tasks = [asyncio.create_task(worker()) for _ in range(count)]
    await asyncio.wait([fill_task, *work_tasks])


class AsyncioLoopingCall:
    """A simple implementation of a periodic call using asyncio, keeping
    some API and behavior compatibility with the Twisted ``LoopingCall``.

    The function is called every *interval* seconds, independent of the finish
    time of the previous call. If the function  is still running when it's time
    to call it again, calls are skipped until the function finishes.

    The function must not return a coroutine or a ``Deferred``.
    """

    def __init__(self, func: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs):
        self._func: Callable[_P, _T] = func
        self._args: tuple[Any, ...] = args
        self._kwargs: dict[str, Any] = kwargs
        self._task: asyncio.Task | None = None
        self.interval: float | None = None
        self._start_time: float | None = None

    @property
    def running(self) -> bool:
        return self._start_time is not None

    def start(self, interval: float, now: bool = True) -> None:
        """Start calling the function every *interval* seconds.

        :param interval: The interval in seconds between calls.
        :type interval: float

        :param now: If ``True``, also call the function immediately.
        :type now: bool
        """
        if self.running:
            raise RuntimeError("AsyncioLoopingCall already running")

        if interval <= 0:
            raise ValueError("Interval must be greater than 0")

        self.interval = interval
        self._start_time = time.time()
        if now:
            self._call()
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._loop())

    def _to_sleep(self) -> float:
        """Return the time to sleep until the next call."""
        assert self.interval is not None
        assert self._start_time is not None
        now = time.time()
        running_for = now - self._start_time
        return self.interval - (running_for % self.interval)

    async def _loop(self) -> None:
        """Run an infinite loop that calls the function periodically."""
        while self.running:
            await asyncio.sleep(self._to_sleep())
            self._call()

    def stop(self) -> None:
        """Stop the periodic calls."""
        self.interval = self._start_time = None
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def _call(self) -> None:
        """Execute the function."""
        try:
            result = self._func(*self._args, **self._kwargs)
        except Exception:
            logger.exception("Error calling the AsyncioLoopingCall function")
            self.stop()
        else:
            if isinstance(result, (Coroutine, Deferred)):
                self.stop()
                raise TypeError(
                    "The AsyncioLoopingCall function must not return a coroutine or a Deferred"
                )


def create_looping_call(
    func: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs
) -> AsyncioLoopingCall | LoopingCall:
    """Create an instance of a looping call class.

    This creates an instance of :class:`AsyncioLoopingCall` or
    :class:`LoopingCall`, depending on whether asyncio support is available.
    """
    if is_asyncio_available():
        return AsyncioLoopingCall(func, *args, **kwargs)
    return LoopingCall(func, *args, **kwargs)


def call_later(
    delay: float, func: Callable[[Unpack[_Ts]], object], *args: Unpack[_Ts]
) -> CallLaterResult:
    """Schedule a function to be called after a delay.

    This uses either ``loop.call_later()`` or ``reactor.callLater()``, depending
    on whether asyncio support is available.
    """
    if is_asyncio_available():
        loop = asyncio.get_event_loop()
        return CallLaterResult.from_asyncio(loop.call_later(delay, func, *args))

    from twisted.internet import reactor

    return CallLaterResult.from_twisted(reactor.callLater(delay, func, *args))


class CallLaterResult:
    """An universal result for :func:`call_later`, wrapping either
    :class:`asyncio.TimerHandle` or :class:`twisted.internet.base.DelayedCall`.

    The provided API is close to the :class:`asyncio.TimerHandle` one: there is
    no ``active()`` (as there is no such public API in
    :class:`asyncio.TimerHandle`) but ``cancel()`` can be called on already
    called or cancelled instances.
    """

    _timer_handle: asyncio.TimerHandle | None = None
    _delayed_call: DelayedCall | None = None

    @classmethod
    def from_asyncio(cls, timer_handle: asyncio.TimerHandle) -> Self:
        """Create a CallLaterResult from an asyncio TimerHandle."""
        o = cls()
        o._timer_handle = timer_handle
        return o

    @classmethod
    def from_twisted(cls, delayed_call: DelayedCall) -> Self:
        """Create a CallLaterResult from a Twisted DelayedCall."""
        o = cls()
        o._delayed_call = delayed_call
        return o

    def cancel(self) -> None:
        """Cancel the underlying delayed call.

        Does nothing if the delayed call was already called or cancelled.
        """
        if self._timer_handle:
            self._timer_handle.cancel()
            self._timer_handle = None
        elif self._delayed_call and self._delayed_call.active():
            self._delayed_call.cancel()
            self._delayed_call = None
