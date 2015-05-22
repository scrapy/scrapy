"""
Helper functions for dealing with Twisted deferreds
"""

from twisted.internet import defer, reactor, task
from twisted.python import failure

from scrapy.exceptions import IgnoreRequest

def defer_fail(_failure):
    """Same as twisted.internet.defer.fail but delay calling errback until
    next reactor loop

    It delays by 100ms so reactor has a chance to go trough readers and writers
    before attending pending delayed calls, so do not set delay to zero.
    """
    d = defer.Deferred()
    reactor.callLater(0.1, d.errback, _failure)
    return d

def defer_succeed(result):
    """Same as twisted.internet.defer.succeed but delay calling callback until
    next reactor loop

    It delays by 100ms so reactor has a chance to go trough readers and writers
    before attending pending delayed calls, so do not set delay to zero.
    """
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
    except:
        return defer_fail(failure.Failure())
    else:
        return defer_result(result)

def parallel(iterable, count, callable, *args, **named):
    """Execute a callable over the objects in the given iterable, in parallel,
    using no more than ``count`` concurrent calls.

    Taken from: http://jcalderone.livejournal.com/24285.html
    """
    coop = task.Cooperator()
    work = (callable(elem, *args, **named) for elem in iterable)
    return defer.DeferredList([coop.coiterate(work) for i in xrange(count)])

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
    while 1:
        try:
            yield next(it)
        except StopIteration:
            break
        except:
            errback(failure.Failure(), *a, **kw)
