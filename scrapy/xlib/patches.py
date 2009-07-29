"""
Monkey patches for supporting Twisted 2.5.0
"""

import twisted

def apply_patches():
    if twisted.__version__ < '8.0.0':
        patch_HTTPPageGetter_handleResponse()
        add_missing_blockingCallFromThread()


# bugfix not present in twisted 2.5 for handling empty response of HEAD requests
def patch_HTTPPageGetter_handleResponse():
    from twisted.web.client import PartialDownloadError, HTTPPageGetter
    from twisted.python import failure
    from twisted.web import error

    def _handleResponse(self, response):
        if self.quietLoss:
            return
        if self.failed:
            self.factory.noPage(
                failure.Failure(
                    error.Error(
                        self.status, self.message, response)))
        if self.factory.method.upper() == 'HEAD':
            # Callback with empty string, since there is never a response
            # body for HEAD requests.
            self.factory.page('')
        elif self.length != None and self.length != 0:
            self.factory.noPage(failure.Failure(
                PartialDownloadError(self.status, self.message, response)))
        else:
            self.factory.page(response)
        # server might be stupid and not close connection. admittedly
        # the fact we do only one request per connection is also
        # stupid...
        self.transport.loseConnection()
    setattr(HTTPPageGetter, 'handleResponse', _handleResponse)

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
