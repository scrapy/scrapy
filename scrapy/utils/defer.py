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
        d.addCallbacks(cb, eb, callbackArgs=a, callbackKeywords=kw,
            errbackArgs=a, errbackKeywords=kw)
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
    d = defer.DeferredList(dfds, fireOnOneErrback=1, consumeErrors=1)
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


def _isfuture(o):
    # workaround for Python before 3.5.3 not having asyncio.isfuture
    if hasattr(asyncio, 'isfuture'):
        return asyncio.isfuture(o)
    return isinstance(o, asyncio.Future)


def deferred_from_coro(o):
    """Converts a coroutine into a Deferred, or returns the object as is if it isn't a coroutine"""
    if isinstance(o, defer.Deferred):
        return o
    if _isfuture(o) or inspect.isawaitable(o):
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
    elif _isfuture(result) or inspect.isawaitable(result):
        return deferred_from_coro(result)
    elif isinstance(result, failure.Failure):
        return defer.fail(result)
    else:
        return defer.succeed(result)
