"""
Helper functions for dealing with Twisted deferreds
"""

from itertools import imap
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
    return d1.chainDeferred(d2).addBoth(lambda _:d2)

def deferred_imap(function, *sequences, **kwargs):
    """Analog to itertools.imap python function but friendly iterable evaluation
    taking in count cooperative multitasking.

    It returns a Deferred object that is fired when StopIteration is reached or
    when any exception is raised when calling function.

    By default the output of the evaluation is collected into a list and
    returned as deferred result when iterable finished. But it can be disabled
    (to save memory) using `store_results` parameter.

    """

    next_delay = kwargs.pop('next_delay', 0)
    store_results = kwargs.pop('store_results', True)

    deferred = defer.Deferred()
    container = []

    iterator = imap(function, *sequences)

    def _next():
        try:
            value = iterator.next()
            if store_results:
                container.append(value)
        except StopIteration:
            reactor.callLater(0, deferred.callback, container)
        except:
            reactor.callLater(0, deferred.errback, failure.Failure())
        else:
            reactor.callLater(next_delay, _next)

    _next()
    return deferred
