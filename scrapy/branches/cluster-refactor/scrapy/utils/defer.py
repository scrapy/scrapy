"""
Helper functions for dealing with Twisted deferreds
"""

from twisted.internet import defer, reactor
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
    if callable(d2):
        d2 = lambda_deferred(d2)

    def _pause(_):
        d2.pause()
        reactor.callLater(0, d2.unpause)
        return _

    def _reclaim(_):
        return d2

    #d1.addBoth(_pause) ## needs more debugging before reenable it
    d1.chainDeferred(d2)
    d1.addBoth(_reclaim)
    return d1

def lambda_deferred(func):
    deferred = defer.Deferred()
    def _success(res):
        d = func()
        d.callback(res)
        return d
    def _fail(res):
        d = func()
        d.errback(res)
        return d
    return deferred.addCallbacks(_success, _fail)

def deferred_degenerate(generator, container=None, next_delay=0):
    generator = iter(generator or [])
    deferred = defer.Deferred()
    container = container or []
    def _next():
        try:
            container.append(generator.next())
        except StopIteration:
            reactor.callLater(0, deferred.callback, container)
        except:
            reactor.callLater(0, deferred.errback, failure.Failure())
        else:
            reactor.callLater(next_delay, _next)
    _next()
    return deferred

