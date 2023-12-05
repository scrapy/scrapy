# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Extended thread dispatching support.

For basic support see reactor threading API docs.
"""


import queue as Queue

from twisted.internet import defer
from twisted.python import failure


def deferToThreadPool(reactor, threadpool, f, *args, **kwargs):
    """
    Call the function C{f} using a thread from the given threadpool and return
    the result as a Deferred.

    This function is only used by client code which is maintaining its own
    threadpool.  To run a function in the reactor's threadpool, use
    C{deferToThread}.

    @param reactor: The reactor in whose main thread the Deferred will be
        invoked.

    @param threadpool: An object which supports the C{callInThreadWithCallback}
        method of C{twisted.python.threadpool.ThreadPool}.

    @param f: The function to call.
    @param args: positional arguments to pass to f.
    @param kwargs: keyword arguments to pass to f.

    @return: A Deferred which fires a callback with the result of f, or an
        errback with a L{twisted.python.failure.Failure} if f throws an
        exception.
    """
    d = defer.Deferred()

    def onResult(success, result):
        if success:
            reactor.callFromThread(d.callback, result)
        else:
            reactor.callFromThread(d.errback, result)

    threadpool.callInThreadWithCallback(onResult, f, *args, **kwargs)

    return d


def deferToThread(f, *args, **kwargs):
    """
    Run a function in a thread and return the result as a Deferred.

    @param f: The function to call.
    @param args: positional arguments to pass to f.
    @param kwargs: keyword arguments to pass to f.

    @return: A Deferred which fires a callback with the result of f,
    or an errback with a L{twisted.python.failure.Failure} if f throws
    an exception.
    """
    from twisted.internet import reactor

    return deferToThreadPool(reactor, reactor.getThreadPool(), f, *args, **kwargs)


def _runMultiple(tupleList):
    """
    Run a list of functions.
    """
    for f, args, kwargs in tupleList:
        f(*args, **kwargs)


def callMultipleInThread(tupleList):
    """
    Run a list of functions in the same thread.

    tupleList should be a list of (function, argsList, kwargsDict) tuples.
    """
    from twisted.internet import reactor

    reactor.callInThread(_runMultiple, tupleList)


def blockingCallFromThread(reactor, f, *a, **kw):
    """
    Run a function in the reactor from a thread, and wait for the result
    synchronously.  If the function returns a L{Deferred}, wait for its
    result and return that.

    @param reactor: The L{IReactorThreads} provider which will be used to
        schedule the function call.
    @param f: the callable to run in the reactor thread
    @type f: any callable.
    @param a: the arguments to pass to C{f}.
    @param kw: the keyword arguments to pass to C{f}.

    @return: the result of the L{Deferred} returned by C{f}, or the result
        of C{f} if it returns anything other than a L{Deferred}.

    @raise Exception: If C{f} raises a synchronous exception,
        C{blockingCallFromThread} will raise that exception.  If C{f}
        returns a L{Deferred} which fires with a L{Failure},
        C{blockingCallFromThread} will raise that failure's exception (see
        L{Failure.raiseException}).
    """
    queue = Queue.Queue()

    def _callFromThread():
        result = defer.maybeDeferred(f, *a, **kw)
        result.addBoth(queue.put)

    reactor.callFromThread(_callFromThread)
    result = queue.get()
    if isinstance(result, failure.Failure):
        result.raiseException()
    return result


__all__ = [
    "deferToThread",
    "deferToThreadPool",
    "callMultipleInThread",
    "blockingCallFromThread",
]
