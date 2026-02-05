"""
Helper functions for dealing with Twisted deferreds
"""

from __future__ import annotations

import asyncio
import inspect
import warnings
from asyncio import Future
from collections.abc import Awaitable, Coroutine, Iterable, Iterator
from functools import wraps
from typing import (
    TYPE_CHECKING,
    Any,
    Concatenate,
    Generic,
    ParamSpec,
    TypeVar,
    cast,
    overload,
)

from twisted.internet.defer import Deferred, DeferredList, fail, succeed
from twisted.internet.task import Cooperator
from twisted.python import failure

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.asyncio import is_asyncio_available
from scrapy.utils.python import global_object_name

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from twisted.python.failure import Failure


_T = TypeVar("_T")
_T2 = TypeVar("_T2")
_P = ParamSpec("_P")


_DEFER_DELAY = 0.1


def defer_fail(_failure: Failure) -> Deferred[Any]:
    """Same as twisted.internet.defer.fail but delay calling errback until
    next reactor loop

    It delays by 100ms so reactor has a chance to go through readers and writers
    before attending pending delayed calls, so do not set delay to zero.
    """
    warnings.warn(
        "scrapy.utils.defer.defer_fail() is deprecated, use"
        " twisted.internet.defer.fail(), plus an explicit sleep if needed.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )

    from twisted.internet import reactor

    d: Deferred[Any] = Deferred()
    reactor.callLater(_DEFER_DELAY, d.errback, _failure)
    return d


def defer_succeed(result: _T) -> Deferred[_T]:
    """Same as twisted.internet.defer.succeed but delay calling callback until
    next reactor loop

    It delays by 100ms so reactor has a chance to go through readers and writers
    before attending pending delayed calls, so do not set delay to zero.
    """
    warnings.warn(
        "scrapy.utils.defer.defer_succeed() is deprecated, use"
        " twisted.internet.defer.succeed(), plus an explicit sleep if needed.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )

    from twisted.internet import reactor

    d: Deferred[_T] = Deferred()
    reactor.callLater(_DEFER_DELAY, d.callback, result)
    return d


async def _defer_sleep_async() -> None:
    """Delay by _DEFER_DELAY so reactor has a chance to go through readers and writers
    before attending pending delayed calls, so do not set delay to zero.
    """
    if is_asyncio_available():
        await asyncio.sleep(_DEFER_DELAY)
    else:
        from twisted.internet import reactor

        d: Deferred[None] = Deferred()
        reactor.callLater(_DEFER_DELAY, d.callback, None)
        await d


def defer_result(result: Any) -> Deferred[Any]:
    warnings.warn(
        "scrapy.utils.defer.defer_result() is deprecated, use"
        " twisted.internet.defer.success() and twisted.internet.defer.fail(),"
        " plus an explicit sleep if needed, or explicit reactor.callLater().",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )

    if isinstance(result, Deferred):
        return result

    from twisted.internet import reactor

    d: Deferred[Any] = Deferred()
    if isinstance(result, failure.Failure):
        reactor.callLater(_DEFER_DELAY, d.errback, result)
    else:
        reactor.callLater(_DEFER_DELAY, d.callback, result)
    return d


@overload
def mustbe_deferred(
    f: Callable[_P, Deferred[_T]], *args: _P.args, **kw: _P.kwargs
) -> Deferred[_T]: ...


@overload
def mustbe_deferred(
    f: Callable[_P, _T], *args: _P.args, **kw: _P.kwargs
) -> Deferred[_T]: ...


def mustbe_deferred(
    f: Callable[_P, Deferred[_T] | _T],
    *args: _P.args,
    **kw: _P.kwargs,
) -> Deferred[_T]:
    """Same as twisted.internet.defer.maybeDeferred, but delay calling
    callback/errback to next reactor loop
    """
    warnings.warn(
        "scrapy.utils.defer.mustbe_deferred() is deprecated, use"
        " twisted.internet.defer.maybeDeferred(), with an explicit sleep if needed.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )
    result: _T | Deferred[_T] | Failure
    try:
        result = f(*args, **kw)
    except Exception:
        result = failure.Failure()
    return defer_result(result)


def parallel(
    iterable: Iterable[_T],
    count: int,
    callable: Callable[Concatenate[_T, _P], _T2],  # noqa: A002
    *args: _P.args,
    **named: _P.kwargs,
) -> Deferred[list[tuple[bool, Iterator[_T2]]]]:
    """Execute a callable over the objects in the given iterable, in parallel,
    using no more than ``count`` concurrent calls.

    Taken from: https://jcalderone.livejournal.com/24285.html
    """
    coop = Cooperator()
    work: Iterator[_T2] = (callable(elem, *args, **named) for elem in iterable)
    return DeferredList([coop.coiterate(work) for _ in range(count)])


class _AsyncCooperatorAdapter(Iterator, Generic[_T]):
    """A class that wraps an async iterable into a normal iterator suitable
    for using in Cooperator.coiterate(). As it's only needed for parallel_async(),
    it calls the callable directly in the callback, instead of providing a more
    generic interface.

    On the outside, this class behaves as an iterator that yields Deferreds.
    Each Deferred is fired with the result of the callable which was called on
    the next result from aiterator. It raises StopIteration when aiterator is
    exhausted, as expected.

    Cooperator calls __next__() multiple times and waits on the Deferreds
    returned from it. As async generators (since Python 3.8) don't support
    awaiting on __anext__() several times in parallel, we need to serialize
    this. It's done by storing the Deferreds returned from __next__() and
    firing the oldest one when a result from __anext__() is available.

    The workflow:
    1. When __next__() is called for the first time, it creates a Deferred, stores it
    in self.waiting_deferreds and returns it. It also makes a Deferred that will wait
    for self.aiterator.__anext__() and puts it into self.anext_deferred.
    2. If __next__() is called again before self.anext_deferred fires, more Deferreds
    are added to self.waiting_deferreds.
    3. When self.anext_deferred fires, it either calls _callback() or _errback(). Both
    clear self.anext_deferred.
    3.1. _callback() calls the callable passing the result value that it takes, pops a
    Deferred from self.waiting_deferreds, and if the callable result was a Deferred, it
    chains those Deferreds so that the waiting Deferred will fire when the result
    Deferred does, otherwise it fires it directly. This causes one awaiting task to
    receive a result. If self.waiting_deferreds is still not empty, new __anext__() is
    called and self.anext_deferred is populated.
    3.2. _errback() checks the exception class. If it's StopAsyncIteration it means
    self.aiterator is exhausted and so it sets self.finished and fires all
    self.waiting_deferreds. Other exceptions are propagated.
    4. If __next__() is called after __anext__() was handled, then if self.finished is
    True, it raises StopIteration, otherwise it acts like in step 2, but if
    self.anext_deferred is now empty is also populates it with a new __anext__().

    Note that CooperativeTask ignores the value returned from the Deferred that it waits
    for, so we fire them with None when needed.

    It may be possible to write an async iterator-aware replacement for
    Cooperator/CooperativeTask and use it instead of this adapter to achieve the same
    goal.
    """

    def __init__(
        self,
        aiterable: AsyncIterator[_T],
        callable_: Callable[Concatenate[_T, _P], Deferred[Any] | None],
        *callable_args: _P.args,
        **callable_kwargs: _P.kwargs,
    ):
        self.aiterator: AsyncIterator[_T] = aiterable.__aiter__()
        self.callable: Callable[Concatenate[_T, _P], Deferred[Any] | None] = callable_
        self.callable_args: tuple[Any, ...] = callable_args
        self.callable_kwargs: dict[str, Any] = callable_kwargs
        self.finished: bool = False
        self.waiting_deferreds: list[Deferred[Any]] = []
        self.anext_deferred: Deferred[_T] | None = None

    def _callback(self, result: _T) -> None:
        # This gets called when the result from aiterator.__anext__() is available.
        # It calls the callable on it and sends the result to the oldest waiting Deferred
        # (by chaining if the result is a Deferred too or by firing if not).
        self.anext_deferred = None
        callable_result = self.callable(
            result, *self.callable_args, **self.callable_kwargs
        )
        d = self.waiting_deferreds.pop(0)
        if isinstance(callable_result, Deferred):
            callable_result.chainDeferred(d)
        else:
            d.callback(None)
        if self.waiting_deferreds:
            self._call_anext()

    def _errback(self, failure: Failure) -> None:
        # This gets called on any exceptions in aiterator.__anext__().
        # It handles StopAsyncIteration by stopping the iteration and reraises all others.
        self.anext_deferred = None
        failure.trap(StopAsyncIteration)
        self.finished = True
        for d in self.waiting_deferreds:
            d.callback(None)

    def _call_anext(self) -> None:
        # This starts waiting for the next result from aiterator.
        # If aiterator is exhausted, _errback will be called.
        self.anext_deferred = deferred_from_coro(self.aiterator.__anext__())
        self.anext_deferred.addCallbacks(self._callback, self._errback)

    def __next__(self) -> Deferred[Any]:
        # This puts a new Deferred into self.waiting_deferreds and returns it.
        # It also calls __anext__() if needed.
        if self.finished:
            raise StopIteration
        d: Deferred[Any] = Deferred()
        self.waiting_deferreds.append(d)
        if not self.anext_deferred:
            self._call_anext()
        return d


def parallel_async(
    async_iterable: AsyncIterator[_T],
    count: int,
    callable: Callable[Concatenate[_T, _P], Deferred[Any] | None],  # noqa: A002
    *args: _P.args,
    **named: _P.kwargs,
) -> Deferred[list[tuple[bool, Iterator[Deferred[Any]]]]]:
    """Like ``parallel`` but for async iterators"""
    coop = Cooperator()
    work: Iterator[Deferred[Any]] = _AsyncCooperatorAdapter(
        async_iterable, callable, *args, **named
    )
    dl: Deferred[list[tuple[bool, Iterator[Deferred[Any]]]]] = DeferredList(
        [coop.coiterate(work) for _ in range(count)]
    )
    return dl


def process_chain(
    callbacks: Iterable[Callable[Concatenate[_T, _P], _T]],
    input: _T,  # noqa: A002
    *a: _P.args,
    **kw: _P.kwargs,
) -> Deferred[_T]:
    """Return a Deferred built by chaining the given callbacks"""
    warnings.warn(
        "process_chain() is deprecated.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )
    d: Deferred[_T] = Deferred()
    for x in callbacks:
        d.addCallback(x, *a, **kw)
    d.callback(input)
    return d


def process_parallel(
    callbacks: Iterable[Callable[Concatenate[_T, _P], _T2]],
    input: _T,  # noqa: A002
    *a: _P.args,
    **kw: _P.kwargs,
) -> Deferred[list[_T2]]:  # pragma: no cover
    """Return a Deferred with the output of all successful calls to the given
    callbacks
    """
    warnings.warn(
        "process_parallel() is deprecated.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )
    dfds = [succeed(input).addCallback(x, *a, **kw) for x in callbacks]
    d: Deferred[list[tuple[bool, _T2]]] = DeferredList(
        dfds, fireOnOneErrback=True, consumeErrors=True
    )
    d2: Deferred[list[_T2]] = d.addCallback(lambda r: [x[1] for x in r])

    def eb(failure: Failure) -> Failure:
        return failure.value.subFailure

    d2.addErrback(eb)
    return d2


def iter_errback(
    iterable: Iterable[_T],
    errback: Callable[Concatenate[Failure, _P], Any],
    *a: _P.args,
    **kw: _P.kwargs,
) -> Iterable[_T]:
    """Wrap an iterable calling an errback if an error is caught while
    iterating it.
    """
    it = iter(iterable)
    while True:
        try:
            yield next(it)
        except StopIteration:
            break
        except Exception:
            errback(failure.Failure(), *a, **kw)


async def aiter_errback(
    aiterable: AsyncIterator[_T],
    errback: Callable[Concatenate[Failure, _P], Any],
    *a: _P.args,
    **kw: _P.kwargs,
) -> AsyncIterator[_T]:
    """Wrap an async iterable calling an errback if an error is caught while
    iterating it. Similar to :func:`scrapy.utils.defer.iter_errback`.
    """
    it = aiterable.__aiter__()
    while True:
        try:
            yield await it.__anext__()
        except StopAsyncIteration:
            break
        except Exception:
            errback(failure.Failure(), *a, **kw)


@overload
def deferred_from_coro(o: Awaitable[_T]) -> Deferred[_T]: ...


@overload
def deferred_from_coro(o: _T2) -> _T2: ...


def deferred_from_coro(o: Awaitable[_T] | _T2) -> Deferred[_T] | _T2:
    """Convert a coroutine or other awaitable object into a Deferred,
    or return the object as is if it isn't a coroutine."""
    if isinstance(o, Deferred):
        return o
    if inspect.isawaitable(o):
        if not is_asyncio_available():
            # wrapping the coroutine directly into a Deferred, this doesn't work correctly with coroutines
            # that use asyncio, e.g. "await asyncio.sleep(1)"
            return Deferred.fromCoroutine(cast("Coroutine[Deferred[Any], Any, _T]", o))
        # wrapping the coroutine into a Future and then into a Deferred, this requires AsyncioSelectorReactor
        return Deferred.fromFuture(asyncio.ensure_future(o))
    return o


def deferred_f_from_coro_f(
    coro_f: Callable[_P, Awaitable[_T]],
) -> Callable[_P, Deferred[_T]]:
    """Convert a coroutine function into a function that returns a Deferred.

    The coroutine function will be called at the time when the wrapper is called. Wrapper args will be passed to it.
    This is useful for callback chains, as callback functions are called with the previous callback result.
    """

    @wraps(coro_f)
    def f(*coro_args: _P.args, **coro_kwargs: _P.kwargs) -> Deferred[_T]:
        return deferred_from_coro(coro_f(*coro_args, **coro_kwargs))

    return f


def maybeDeferred_coro(
    f: Callable[_P, Any], *args: _P.args, **kw: _P.kwargs
) -> Deferred[Any]:  # pragma: no cover
    """Copy of defer.maybeDeferred that also converts coroutines to Deferreds."""
    warnings.warn(
        "maybeDeferred_coro() is deprecated and will be removed in a future Scrapy version.",
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    return _maybeDeferred_coro(f, False, *args, **kw)


def _maybeDeferred_coro(
    f: Callable[_P, Any], warn: bool, *args: _P.args, **kw: _P.kwargs
) -> Deferred[Any]:
    """Copy of defer.maybeDeferred that also converts coroutines to Deferreds."""
    try:
        result = f(*args, **kw)
    except:  # noqa: E722  # pylint: disable=bare-except
        return fail(failure.Failure(captureVars=Deferred.debug))

    # when the deprecation period has ended we need to make sure the behavior
    # of the public maybeDeferred_coro() function isn't changed, or drop it in
    # the same release
    if isinstance(result, Deferred):
        if warn:
            warnings.warn(
                f"{global_object_name(f)} returned a Deferred, this is deprecated."
                f" Please refactor this function to return a coroutine.",
                ScrapyDeprecationWarning,
                stacklevel=2,
            )
        return result
    if asyncio.isfuture(result) or inspect.isawaitable(result):
        return deferred_from_coro(result)
    if isinstance(result, failure.Failure):
        if warn:
            warnings.warn(
                f"{global_object_name(f)} returned a Failure, this is deprecated."
                f" Please refactor this function to return a coroutine.",
                ScrapyDeprecationWarning,
                stacklevel=2,
            )
        return fail(result)
    return succeed(result)


def deferred_to_future(d: Deferred[_T]) -> Future[_T]:
    """Return an :class:`asyncio.Future` object that wraps *d*.

    This function requires
    :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor` to be
    installed.

    When :ref:`using the asyncio reactor <install-asyncio>`, you cannot await
    on :class:`~twisted.internet.defer.Deferred` objects from :ref:`Scrapy
    callables defined as coroutines <coroutine-support>`, you can only await on
    ``Future`` objects. Wrapping ``Deferred`` objects into ``Future`` objects
    allows you to wait on them::

        class MySpider(Spider):
            ...
            async def parse(self, response):
                additional_request = scrapy.Request('https://example.org/price')
                deferred = self.crawler.engine.download(additional_request)
                additional_response = await deferred_to_future(deferred)

    .. versionchanged:: 2.14
        This function no longer installs an asyncio loop if called before the
        Twisted asyncio reactor is installed. A :exc:`RuntimeError` is raised
        in this case.
    """
    if not is_asyncio_available():
        raise RuntimeError("deferred_to_future() requires AsyncioSelectorReactor.")
    return d.asFuture(asyncio.get_event_loop())


def maybe_deferred_to_future(d: Deferred[_T]) -> Deferred[_T] | Future[_T]:
    """Return *d* as an object that can be awaited from a :ref:`Scrapy callable
    defined as a coroutine <coroutine-support>`.

    What you can await in Scrapy callables defined as coroutines depends on the
    value of :setting:`TWISTED_REACTOR`:

    -   When :ref:`using the asyncio reactor <install-asyncio>`, you can only
        await on :class:`asyncio.Future` objects.

    -   When not using the asyncio reactor, you can only await on
        :class:`~twisted.internet.defer.Deferred` objects.

    If you want to write code that uses ``Deferred`` objects but works with any
    reactor, use this function on all ``Deferred`` objects::

        class MySpider(Spider):
            ...
            async def parse(self, response):
                additional_request = scrapy.Request('https://example.org/price')
                deferred = self.crawler.engine.download(additional_request)
                additional_response = await maybe_deferred_to_future(deferred)
    """
    if not is_asyncio_available():
        return d
    return deferred_to_future(d)


def _schedule_coro(coro: Coroutine[Any, Any, Any]) -> None:
    """Schedule the coroutine as a task or a Deferred.

    This doesn't store the reference to the task/Deferred, so a better
    alternative is calling :func:`scrapy.utils.defer.deferred_from_coro`,
    keeping the result, and adding proper exception handling (e.g. errbacks) to
    it.
    """
    if not is_asyncio_available():
        Deferred.fromCoroutine(coro)
        return
    loop = asyncio.get_event_loop()
    loop.create_task(coro)  # noqa: RUF006


@overload
def ensure_awaitable(o: Awaitable[_T], _warn: str | None = None) -> Awaitable[_T]: ...


@overload
def ensure_awaitable(o: _T, _warn: str | None = None) -> Awaitable[_T]: ...


def ensure_awaitable(o: _T | Awaitable[_T], _warn: str | None = None) -> Awaitable[_T]:
    """Convert any value to an awaitable object.

    For a :class:`~twisted.internet.defer.Deferred` object, use
    :func:`maybe_deferred_to_future` to wrap it into a suitable object. For an
    awaitable object of a different type, return it as is. For any other
    value, return a coroutine that completes with that value.

    .. versionadded:: 2.14
    """
    if isinstance(o, Deferred):
        if _warn:
            warnings.warn(
                f"{_warn} returned a Deferred, this is deprecated."
                f" Please refactor this function to return a coroutine.",
                ScrapyDeprecationWarning,
                stacklevel=2,
            )
        return maybe_deferred_to_future(o)
    if inspect.isawaitable(o):
        return o

    async def coro() -> _T:
        return o

    return coro()
