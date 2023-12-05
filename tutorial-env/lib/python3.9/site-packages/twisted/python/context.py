# -*- test-case-name: twisted.test.test_context -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Dynamic pseudo-scoping for Python.

Call functions with context.call({key: value}, func); func and
functions that it calls will be able to use 'context.get(key)' to
retrieve 'value'.

This is thread-safe.
"""


from threading import local
from typing import Dict, Type

defaultContextDict: Dict[Type[object], Dict[str, str]] = {}

setDefault = defaultContextDict.__setitem__


class ContextTracker:
    """
    A L{ContextTracker} provides a way to pass arbitrary key/value data up and
    down a call stack without passing them as parameters to the functions on
    that call stack.

    This can be useful when functions on the top and bottom of the call stack
    need to cooperate but the functions in between them do not allow passing the
    necessary state.  For example::

        from twisted.python.context import call, get

        def handleRequest(request):
            call({'request-id': request.id}, renderRequest, request.url)

        def renderRequest(url):
            renderHeader(url)
            renderBody(url)

        def renderHeader(url):
            return "the header"

        def renderBody(url):
            return "the body (request id=%r)" % (get("request-id"),)

    This should be used sparingly, since the lack of a clear connection between
    the two halves can result in code which is difficult to understand and
    maintain.

    @ivar contexts: A C{list} of C{dict}s tracking the context state.  Each new
        L{ContextTracker.callWithContext} pushes a new C{dict} onto this stack
        for the duration of the call, making the data available to the function
        called and restoring the previous data once it is complete..
    """

    def __init__(self):
        self.contexts = [defaultContextDict]

    def callWithContext(self, newContext, func, *args, **kw):
        """
        Call C{func(*args, **kw)} such that the contents of C{newContext} will
        be available for it to retrieve using L{getContext}.

        @param newContext: A C{dict} of data to push onto the context for the
            duration of the call to C{func}.

        @param func: A callable which will be called.

        @param args: Any additional positional arguments to pass to C{func}.

        @param kw: Any additional keyword arguments to pass to C{func}.

        @return: Whatever is returned by C{func}

        @raise Exception: Whatever is raised by C{func}.
        """
        self.contexts.append(newContext)
        try:
            return func(*args, **kw)
        finally:
            self.contexts.pop()

    def getContext(self, key, default=None):
        """
        Retrieve the value for a key from the context.

        @param key: The key to look up in the context.

        @param default: The value to return if C{key} is not found in the
            context.

        @return: The value most recently remembered in the context for C{key}.
        """
        for ctx in reversed(self.contexts):
            try:
                return ctx[key]
            except KeyError:
                pass
        return default


class ThreadedContextTracker:
    def __init__(self):
        self.storage = local()

    def currentContext(self):
        try:
            return self.storage.ct
        except AttributeError:
            ct = self.storage.ct = ContextTracker()
            return ct

    def callWithContext(self, ctx, func, *args, **kw):
        return self.currentContext().callWithContext(ctx, func, *args, **kw)

    def getContext(self, key, default=None):
        return self.currentContext().getContext(key, default)


theContextTracker = ThreadedContextTracker()
call = theContextTracker.callWithContext
get = theContextTracker.getContext


def installContextTracker(ctr):
    global theContextTracker
    global call
    global get

    theContextTracker = ctr
    call = theContextTracker.callWithContext
    get = theContextTracker.getContext
