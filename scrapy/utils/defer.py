"""
Helper functions for dealing with Twisted deferreds
"""
import asyncio
import inspect
from asyncio import Future
from functools import wraps
from typing import (
    Any,
    Callable,
    Coroutine,
    Generator,
    Iterable,
    Union
)

from twisted.internet import defer
from twisted.internet.defer import Deferred, DeferredList, ensureDeferred
from twisted.internet.task import Cooperator
from twisted.python import failure
from twisted.python.failure import Failure

from scrapy.exceptions import IgnoreRequest
from scrapy.utils.reactor import is_asyncio_reactor_installed


def defer_fail(_failure: Failure) -> Deferred:
    """Same as twisted.internet.defer.fail but delay calling errback until
    next reactor loop

    It delays by 100ms so reactor has a chance to go through readers and writers
    before attending pending delayed calls, so do not set delay to zero.
    """
    from twisted.internet import reactor
    d = Deferred()
    reactor.callLater(0.1, d.errback, _failure)
    return d


def defer_succeed(result) -> Deferred:
    """Same as twisted.internet.defer.succeed but delay calling callback until
    next reactor loop

    It delays by 100ms so reactor has a chance to go through readers and writers
    before attending pending delayed calls, so do not set delay to zero.
    """
    from twisted.internet import reactor
    d = Deferred()
    reactor.callLater(0.1, d.callback, result)
    return d


def defer_result(result) -> Deferred:
    if isinstance(result, Deferred):
        return result
    elif isinstance(result, failure.Failure):
        return defer_fail(result)
    else:
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


def parallel(iterable: Iterable, count: int, callable: Callable, *args, **named) -> DeferredList:
    """Execute a callable over the objects in the given iterable, in parallel,
    using no more than ``count`` concurrent calls.

    Taken from: https://jcalderone.livejournal.com/24285.html
    """
    coop = Cooperator()
    work = (callable(elem, *args, **named) for elem in iterable)
    return DeferredList([coop.coiterate(work) for _ in range(count)])


def process_chain(callbacks: Iterable[Callable], input, *a, **kw) -> Deferred:
    """Return a Deferred built by chaining the given callbacks"""
    d = Deferred()
    for x in callbacks:
        d.addCallback(x, *a, **kw)
    d.callback(input)
    return d


def process_chain_both(callbacks: Iterable[Callable], errbacks: Iterable[Callable], input, *a, **kw) -> Deferred:
    """Return a Deferred built by chaining the given callbacks and errbacks"""
    d = Deferred()
    for cb, eb in zip(callbacks, errbacks):
        d.addCallbacks(
            callback=cb, errback=eb,
            callbackArgs=a, callbackKeywords=kw,
            errbackArgs=a, errbackKeywords=kw,
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
    d = DeferredList(dfds, fireOnOneErrback=True, consumeErrors=True)
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


def deferred_from_coro(o) -> Any:
    """Converts a coroutine into a Deferred, or returns the object as is if it isn't a coroutine"""
    if isinstance(o, Deferred):
        return o
    if asyncio.isfuture(o) or inspect.isawaitable(o):
        if not is_asyncio_reactor_installed():
            # wrapping the coroutine directly into a Deferred, this doesn't work correctly with coroutines
            # that use asyncio, e.g. "await asyncio.sleep(1)"
            return ensureDeferred(o)
        else:
            # wrapping the coroutine into a Future and then into a Deferred, this requires AsyncioSelectorReactor
            return Deferred.fromFuture(asyncio.ensure_future(o))
    return o


def deferred_f_from_coro_f(coro_f: Callable[..., Coroutine]) -> Callable:
    """ Converts a coroutine function into a function that returns a Deferred.

    The coroutine function will be called at the time when the wrapper is called. Wrapper args will be passed to it.
    This is useful for callback chains, as callback functions are called with the previous callback result.
    """
    @wraps(coro_f)
    def f(*coro_args, **coro_kwargs):
        return deferred_from_coro(coro_f(*coro_args, **coro_kwargs))
    return f


def maybeDeferred_coro(f: Callable, *args, **kw) -> Deferred:
    """ Copy of defer.maybeDeferred that also converts coroutines to Deferreds. """
    try:
        result = f(*args, **kw)
    except:  # noqa: E722
        return defer.fail(failure.Failure(captureVars=Deferred.debug))

    if isinstance(result, Deferred):
        return result
    elif asyncio.isfuture(result) or inspect.isawaitable(result):
        return deferred_from_coro(result)
    elif isinstance(result, failure.Failure):
        return defer.fail(result)
    else:
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
    return d.asFuture(asyncio.get_event_loop())


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
    else:
        return deferred_to_future(d)
