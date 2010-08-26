"""
Monkey patches for supporting Twisted 2.5.0

NOTE: This module must not fail if twisted module is not available.
"""

# This function comes bundled with Twisted 8.x and above
def add_missing_blockingCallFromThread():
    import Queue
    from twisted.internet import defer
    from twisted.python import failure

    def blockingCallFromThread(reactor, f, *a, **kw):
        """
        Run a function in the reactor from a thread, and wait for the result
        synchronously, i.e. until the callback chain returned by the function
        get a result.

        @param reactor: The L{IReactorThreads} provider which will be used to
            schedule the function call.
        @param f: the callable to run in the reactor thread
        @type f: any callable.
        @param a: the arguments to pass to C{f}.
        @param kw: the keyword arguments to pass to C{f}.

        @return: the result of the callback chain.
        @raise: any error raised during the callback chain.
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

    from twisted.internet import threads
    threads.blockingCallFromThread = blockingCallFromThread

try:
    import twisted
    from twisted.python.versions import Version
    if twisted.version < Version("twisted", 8, 0, 0):
        add_missing_blockingCallFromThread()
except ImportError:
    pass

