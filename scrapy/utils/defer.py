"""
Helper functions for dealing with Twisted deferreds
"""
import asyncio
import inspect
from functools import wraps

from twisted.internet import defer, task
from twisted.python import failure

from scrapy.exceptions import IgnoreRequest
from scrapy.utils.reactor import is_asyncio_reactor_installed


def defer_fail(_failure):
    """Same as twisted.internet.defer.fail but delay calling errback until
    next reactor loop

    It delays by 100ms so reactor has a chance to go through readers and writers
    before attending pending delayed calls, so do not set delay to zero.
    """
    from twisted.internet import reactor
    d = defer.Deferred()
    reactor.callLater(0.1, d.errback, _failure)
    return d


def defer_succeed(result):
    """Same as twisted.internet.defer.succeed but delay calling callback until
    next reactor loop

    It delays by 100ms so reactor has a chance to go trough readers and writers
    before attending pending delayed calls, so do not set delay to zero.
    """
    from twisted.internet import reactor
    d = defer.Deferred()
    reactor.callLater(0.1, d.callback, result)
    return d


def defer_result(result):
    if isinstance(result, defer.Deferred):
        return result
    elif isinstance(result, failure.Failure):
        return defer_fail(result)
    else:
        return defer_succeed(result)


def mustbe_deferred(f, *args, **kw):
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


def parallel(iterable, count, callable, *args, **named):
    """Execute a callable over the objects in the given iterable, in parallel,
    using no more than ``count`` concurrent calls.

    Taken from: https://jcalderone.livejournal.com/24285.html
    """
    coop = task.Cooperator()
    work = (callable(elem, *args, **named) for elem in iterable)
    return defer.DeferredList([coop.coiterate(work) for _ in range(count)])


class _AsyncCooperatorAdapter:
    """ A class that wraps an async iterator into a normal iterator suitable
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
    def __init__(self, aiterator, callable, *callable_args, **callable_kwargs):
        self.aiterator = aiterator
        self.callable = callable
        self.callable_args = callable_args
        self.callable_kwargs = callable_kwargs
        self.finished = False
        self.waiting_deferreds = []
        self.anext_deferred = None

    def _callback(self, result):
        # This gets called when the result from aiterator.__anext__() is available.
        # It calls the callable on it and sends the result to the oldest waiting Deferred
        # (by chaining if the result is a Deferred too or by firing if not).
        self.anext_deferred = None
        result = self.callable(result, *self.callable_args, **self.callable_kwargs)
        d = self.waiting_deferreds.pop(0)
        if d.called:
            raise ValueError('Deferred in waiting_deferreds already called')
        if isinstance(result, defer.Deferred):
            result.chainDeferred(d)
        else:
            d.callback(None)
        if self.waiting_deferreds:
            self._call_anext()

    def _errback(self, failure):
        # This gets called on any exceptions in aiterator.__anext__().
        # It handles StopAsyncIteration by stopping the iteration and reraises all others.
        self.anext_deferred = None
        failure.trap(StopAsyncIteration)
        self.finished = True
        for d in self.waiting_deferreds:
            if d.called:
                raise ValueError('Deferred in waiting_deferreds already called')
            d.callback(None)

    def _call_anext(self):
        # This starts waiting for the next result from aiterator.
        # If aiterator is exhausted, _errback will be called.
        self.anext_deferred = deferred_from_coro(self.aiterator.__anext__())
        self.anext_deferred.addCallbacks(self._callback, self._errback)

    def __iter__(self):
        return self

    def __next__(self):
        # This puts a new Deferred into self.waiting_deferreds and returns it.
        # It also calls __anext__() if needed.
        if self.finished:
            raise StopIteration
        d = defer.Deferred()
        self.waiting_deferreds.append(d)
        if not self.anext_deferred:
            self._call_anext()
        return d


def parallel_async(async_iterable, count, callable, *args, **named):
    """ Like parallel but for async iterables """
    coop = task.Cooperator()
    work = _AsyncCooperatorAdapter(async_iterable, callable, *args, **named)
    dl = defer.DeferredList([coop.coiterate(work) for _ in range(count)])
    return dl


def process_chain(callbacks, input, *a, **kw):
    """Return a Deferred built by chaining the given callbacks"""
    d = defer.Deferred()
    for x in callbacks:
        d.addCallback(x, *a, **kw)
    d.callback(input)
    return d


def process_chain_both(callbacks, errbacks, input, *a, **kw):
    """Return a Deferred built by chaining the given callbacks and errbacks"""
    d = defer.Deferred()
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


def process_parallel(callbacks, input, *a, **kw):
    """Return a Deferred with the output of all successful calls to the given
    callbacks
    """
    dfds = [defer.succeed(input).addCallback(x, *a, **kw) for x in callbacks]
    d = defer.DeferredList(dfds, fireOnOneErrback=True, consumeErrors=True)
    d.addCallbacks(lambda r: [x[1] for x in r], lambda f: f.value.subFailure)
    return d


def iter_errback(iterable, errback, *a, **kw):
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


async def aiter_errback(aiterable, errback, *a, **kw):
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


def deferred_from_coro(o):
    """Converts a coroutine into a Deferred, or returns the object as is if it isn't a coroutine"""
    if isinstance(o, defer.Deferred):
        return o
    if asyncio.isfuture(o) or inspect.isawaitable(o):
        if not is_asyncio_reactor_installed():
            # wrapping the coroutine directly into a Deferred, this doesn't work correctly with coroutines
            # that use asyncio, e.g. "await asyncio.sleep(1)"
            return defer.ensureDeferred(o)
        else:
            # wrapping the coroutine into a Future and then into a Deferred, this requires AsyncioSelectorReactor
            return defer.Deferred.fromFuture(asyncio.ensure_future(o))
    return o


def deferred_f_from_coro_f(coro_f):
    """ Converts a coroutine function into a function that returns a Deferred.

    The coroutine function will be called at the time when the wrapper is called. Wrapper args will be passed to it.
    This is useful for callback chains, as callback functions are called with the previous callback result.
    """
    @wraps(coro_f)
    def f(*coro_args, **coro_kwargs):
        return deferred_from_coro(coro_f(*coro_args, **coro_kwargs))
    return f


def maybeDeferred_coro(f, *args, **kw):
    """ Copy of defer.maybeDeferred that also converts coroutines to Deferreds. """
    try:
        result = f(*args, **kw)
    except:  # noqa: E722
        return defer.fail(failure.Failure(captureVars=defer.Deferred.debug))

    if isinstance(result, defer.Deferred):
        return result
    elif asyncio.isfuture(result) or inspect.isawaitable(result):
        return deferred_from_coro(result)
    elif isinstance(result, failure.Failure):
        return defer.fail(result)
    else:
        return defer.succeed(result)
