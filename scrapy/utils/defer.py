"""
Helper functions for dealing with Twisted deferreds
"""

from twisted.internet import defer, reactor, task
from twisted.python import failure

from scrapy.exceptions import IgnoreRequest

def defer_fail(_failure):
    """Same as twisted.internet.defer.fail, but delay calling errback until
    next reactor loop
    """
    d = defer.Deferred()
    reactor.callLater(0, d.errback, _failure)
    return d

def defer_succeed(result):
    """Same as twsited.internet.defer.succed, but delay calling callback until
    next reactor loop
    """
    d = defer.Deferred()
    reactor.callLater(0, d.callback, result)
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
    except IgnoreRequest, e:
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
