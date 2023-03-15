"""
Helper functions for dealing with Twisted deferreds
"""
import asyncio
import inspect
from asyncio import Future
from functools import wraps
from typing import (
    Any,
    AsyncGenerator,
    AsyncIterable,
    Callable,
    Coroutine,
    Generator,
    Iterable,
    Iterator,
    List,
    Optional,
    Union,
    cast,
)

from twisted.internet import defer
from twisted.internet.defer import Deferred, DeferredList, ensureDeferred
from twisted.internet.task import Cooperator
from twisted.python import failure
from twisted.python.failure import Failure

from scrapy.exceptions import IgnoreRequest
from scrapy.utils.reactor import _get_asyncio_event_loop, is_asyncio_reactor_installed


def defer_fail(_failure: Failure) -> Deferred:
    """Same as twisted.internet.defer.fail but delay calling errback until
    next reactor loop

    It delays by 100ms so reactor has a chance to go through readers and writers
    before attending pending delayed calls, so do not set delay to zero.
    """
    from twisted.internet import reactor

    d: Deferred = Deferred()
    reactor.callLater(0.1, d.errback, _failure)
    return d


def defer_succeed(result) -> Deferred:
    """Same as twisted.internet.defer.succeed but delay calling callback until
    next reactor loop

    It delays by 100ms so reactor has a chance to go through readers and writers
    before attending pending delayed calls, so do not set delay to zero.
    """
    from twisted.internet import reactor

    d: Deferred = Deferred()
    reactor.callLater(0.1, d.callback, result)
    return d


def defer_result(result) -> Deferred:
    if isinstance(result, Deferred):
        return result
    if isinstance(result, failure.Failure):
        return defer_fail(result)
    return defer_succeed(result)


def mustbe_deferred(f: Callable, *args, **kw) -> Deferred:
    """Same as twisted.internet.defer.maybeDeferred, but delay calling
    callback/errback to next reactor loop
    """
    try:
        result = f(*args, **kw)
    # FIXME: Hack to avoid introspecting tracebacks. This to speed up
    # processing of IgnoreRequest errors which are, by far, the most common
    # exception in Scrapy - see #125
    except IgnoreRequest as e:
        return defer_fail(failure.Failure(e))
    except Exception:
        return defer_fail(failure.Failure())
    else:
        return defer_result(result)


def parallel(
    iterable: Iterable, count: int, callable: Callable, *args, **named
) -> Deferred:
    """Execute a callable over the objects in the given iterable, in parallel,
    using no more than ``count`` concurrent calls.

    Taken from: https://jcalderone.livejournal.com/24285.html
    """
    coop = Cooperator()
    work = (callable(elem, *args, **named) for elem in iterable)
    return DeferredList([coop.coiterate(work) for _ in range(count)])


class _AsyncCooperatorAdapter(Iterator):
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
        aiterable: AsyncIterable,
        callable: Callable,
        *callable_args,
        **callable_kwargs
    ):
        self.aiterator = aiterable.__aiter__()
        self.callable = callable
        self.callable_args = callable_args
        self.callable_kwargs = callable_kwargs
        self.finished = False
        self.waiting_deferreds: List[Deferred] = []
        self.anext_deferred: Optional[Deferred] = None

    def _callback(self, result: Any) -> None:
        # This gets called when the result from aiterator.__anext__() is available.
        # It calls the callable on it and sends the result to the oldest waiting Deferred
        # (by chaining if the result is a Deferred too or by firing if not).
        self.anext_deferred = None
        result = self.callable(result, *self.callable_args, **self.callable_kwargs)
        d = self.waiting_deferreds.pop(0)
        if isinstance(result, Deferred):
            result.chainDeferred(d)
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
        self.anext_deferred = cast(
            Deferred, deferred_from_coro(self.aiterator.__anext__())
        )
        self.anext_deferred.addCallbacks(self._callback, self._errback)

    def __next__(self) -> Deferred:
        # This puts a new Deferred into self.waiting_deferreds and returns it.
        # It also calls __anext__() if needed.
        if self.finished:
            raise StopIteration
        d: Deferred = Deferred()
        self.waiting_deferreds.append(d)
        if not self.anext_deferred:
            self._call_anext()
        return d


def parallel_async(
    async_iterable: AsyncIterable, count: int, callable: Callable, *args, **named
) -> Deferred:
    """Like parallel but for async iterators"""
    coop = Cooperator()
    work = _AsyncCooperatorAdapter(async_iterable, callable, *args, **named)
    dl: Deferred = DeferredList([coop.coiterate(work) for _ in range(count)])
    return dl


def process_chain(callbacks: Iterable[Callable], input, *a, **kw) -> Deferred:
    """Return a Deferred built by chaining the given callbacks"""
    d: Deferred = Deferred()
    for x in callbacks:
        d.addCallback(x, *a, **kw)
    d.callback(input)
    return d


def process_chain_both(
    callbacks: Iterable[Callable], errbacks: Iterable[Callable], input, *a, **kw
) -> Deferred:
    """Return a Deferred built by chaining the given callbacks and errbacks"""
    d: Deferred = Deferred()
    for cb, eb in zip(callbacks, errbacks):
        d.addCallbacks(
            callback=cb,
            errback=eb,
            callbackArgs=a,
            callbackKeywords=kw,
            errbackArgs=a,
            errbackKeywords=kw,
        )
    if isinstance(input, failure.Failure):
        d.errback(input)
    else:
        d.callback(input)
    return d


def process_parallel(callbacks: Iterable[Callable], input, *a, **kw) -> Deferred:
    """Return a Deferred with the output of all successful calls to the given
    callbacks
    """
    dfds = [defer.succeed(input).addCallback(x, *a, **kw) for x in callbacks]
    d: Deferred = DeferredList(dfds, fireOnOneErrback=True, consumeErrors=True)
    d.addCallbacks(lambda r: [x[1] for x in r], lambda f: f.value.subFailure)
    return d


def iter_errback(iterable: Iterable, errback: Callable, *a, **kw) -> Generator:
    """Wraps an iterable calling an errback if an error is caught while
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
    aiterable: AsyncIterable, errback: Callable, *a, **kw
) -> AsyncGenerator:
    """Wraps an async iterable calling an errback if an error is caught while
    iterating it. Similar to scrapy.utils.defer.iter_errback()
    """
    it = aiterable.__aiter__()
    while True:
        try:
            yield await it.__anext__()
        except StopAsyncIteration:
            break
        except Exception:
            errback(failure.Failure(), *a, **kw)


def deferred_from_coro(o) -> Any:
    """Converts a coroutine into a Deferred, or returns the object as is if it isn't a coroutine"""
    if isinstance(o, Deferred):
        return o
    if asyncio.isfuture(o) or inspect.isawaitable(o):
        if not is_asyncio_reactor_installed():
            # wrapping the coroutine directly into a Deferred, this doesn't work correctly with coroutines
            # that use asyncio, e.g. "await asyncio.sleep(1)"
            return ensureDeferred(cast(Coroutine[Deferred, Any, Any], o))
        # wrapping the coroutine into a Future and then into a Deferred, this requires AsyncioSelectorReactor
        event_loop = _get_asyncio_event_loop()
        return Deferred.fromFuture(asyncio.ensure_future(o, loop=event_loop))
    return o


def deferred_f_from_coro_f(coro_f: Callable[..., Coroutine]) -> Callable:
    """Converts a coroutine function into a function that returns a Deferred.

    The coroutine function will be called at the time when the wrapper is called. Wrapper args will be passed to it.
    This is useful for callback chains, as callback functions are called with the previous callback result.
    """

    @wraps(coro_f)
    def f(*coro_args, **coro_kwargs):
        return deferred_from_coro(coro_f(*coro_args, **coro_kwargs))

    return f


def maybeDeferred_coro(f: Callable, *args, **kw) -> Deferred:
    """Copy of defer.maybeDeferred that also converts coroutines to Deferreds."""
    try:
        result = f(*args, **kw)
    except:  # noqa: E722
        return defer.fail(failure.Failure(captureVars=Deferred.debug))

    if isinstance(result, Deferred):
        return result
    if asyncio.isfuture(result) or inspect.isawaitable(result):
        return deferred_from_coro(result)
    if isinstance(result, failure.Failure):
        return defer.fail(result)
    return defer.succeed(result)


def deferred_to_future(d: Deferred) -> Future:
    """
    .. versionadded:: 2.6.0

    Return an :class:`asyncio.Future` object that wraps *d*.

    When :ref:`using the asyncio reactor <install-asyncio>`, you cannot await
    on :class:`~twisted.internet.defer.Deferred` objects from :ref:`Scrapy
    callables defined as coroutines <coroutine-support>`, you can only await on
    ``Future`` objects. Wrapping ``Deferred`` objects into ``Future`` objects
    allows you to wait on them::

        class MySpider(Spider):
            ...
            async def parse(self, response):
                d = treq.get('https://example.com/additional')
                additional_response = await deferred_to_future(d)
    """
    return d.asFuture(_get_asyncio_event_loop())


def maybe_deferred_to_future(d: Deferred) -> Union[Deferred, Future]:
    """
    .. versionadded:: 2.6.0

    Return *d* as an object that can be awaited from a :ref:`Scrapy callable
    defined as a coroutine <coroutine-support>`.

    What you can await in Scrapy callables defined as coroutines depends on the
    value of :setting:`TWISTED_REACTOR`:

    -   When not using the asyncio reactor, you can only await on
        :class:`~twisted.internet.defer.Deferred` objects.

    -   When :ref:`using the asyncio reactor <install-asyncio>`, you can only
        await on :class:`asyncio.Future` objects.

    If you want to write code that uses ``Deferred`` objects but works with any
    reactor, use this function on all ``Deferred`` objects::

        class MySpider(Spider):
            ...
            async def parse(self, response):
                d = treq.get('https://example.com/additional')
                extra_response = await maybe_deferred_to_future(d)
    """
    if not is_asyncio_reactor_installed():
        return d
    return deferred_to_future(d)
