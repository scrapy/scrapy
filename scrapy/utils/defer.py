"""
Helper functions for dealing with Twisted deferreds
"""

from twisted.internet import defer, reactor, task
from twisted.python import failure

def defer_fail(_failure):
    """same as twsited.internet.defer.fail, but delay calling errback """
    d = defer.Deferred()
    reactor.callLater(0, d.errback, _failure)
    return d

def defer_succeed(result):
    """same as twsited.internet.defer.succed, but delay calling callback"""
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
    """same as twisted.internet.defer.maybeDeferred, but delay calling callback/errback"""
    try:
        result = f(*args, **kw)
    except:
        return defer_fail(failure.Failure())
    else:
        return defer_result(result)

def chain_deferred(d1, d2):
    return d1.chainDeferred(d2).addBoth(lambda _:d2)

def parallel(iterable, count, callable, *args, **named):
    """Execute a callable over the objects in the given iterable, in parallel,
    using no more than ``count`` concurrent calls.

    Taken from: http://jcalderone.livejournal.com/24285.html
    """
    coop = task.Cooperator()
    work = (callable(elem, *args, **named) for elem in iterable)
    return defer.DeferredList([coop.coiterate(work) for i in xrange(count)])

