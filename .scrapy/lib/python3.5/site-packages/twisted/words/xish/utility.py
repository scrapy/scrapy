# -*- test-case-name: twisted.words.test.test_xishutil -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Event Dispatching and Callback utilities.
"""

from __future__ import absolute_import, division

from twisted.python import log
from twisted.python.compat import iteritems
from twisted.words.xish import xpath

class _MethodWrapper(object):
    """
    Internal class for tracking method calls.
    """
    def __init__(self, method, *args, **kwargs):
        self.method = method
        self.args = args
        self.kwargs = kwargs


    def __call__(self, *args, **kwargs):
        nargs = self.args + args
        nkwargs = self.kwargs.copy()
        nkwargs.update(kwargs)
        self.method(*nargs, **nkwargs)



class CallbackList:
    """
    Container for callbacks.

    Event queries are linked to lists of callables. When a matching event
    occurs, these callables are called in sequence. One-time callbacks
    are removed from the list after the first time the event was triggered.

    Arguments to callbacks are split spread across two sets. The first set,
    callback specific, is passed to C{addCallback} and is used for all
    subsequent event triggers.  The second set is passed to C{callback} and is
    event specific. Positional arguments in the second set come after the
    positional arguments of the first set. Keyword arguments in the second set
    override those in the first set.

    @ivar callbacks: The registered callbacks as mapping from the callable to a
                     tuple of a wrapper for that callable that keeps the
                     callback specific arguments and a boolean that signifies
                     if it is to be called only once.
    @type callbacks: C{dict}
    """

    def __init__(self):
        self.callbacks = {}


    def addCallback(self, onetime, method, *args, **kwargs):
        """
        Add callback.

        The arguments passed are used as callback specific arguments.

        @param onetime: If C{True}, this callback is called at most once.
        @type onetime: C{bool}
        @param method: The callback callable to be added.
        @param args: Positional arguments to the callable.
        @type args: C{list}
        @param kwargs: Keyword arguments to the callable.
        @type kwargs: C{dict}
        """

        if not method in self.callbacks:
            self.callbacks[method] = (_MethodWrapper(method, *args, **kwargs),
                                      onetime)


    def removeCallback(self, method):
        """
        Remove callback.

        @param method: The callable to be removed.
        """

        if method in self.callbacks:
            del self.callbacks[method]


    def callback(self, *args, **kwargs):
        """
        Call all registered callbacks.

        The passed arguments are event specific and augment and override
        the callback specific arguments as described above.

        @note: Exceptions raised by callbacks are trapped and logged. They will
               not propagate up to make sure other callbacks will still be
               called, and the event dispatching always succeeds.

        @param args: Positional arguments to the callable.
        @type args: C{list}
        @param kwargs: Keyword arguments to the callable.
        @type kwargs: C{dict}
        """

        for key, (methodwrapper, onetime) in list(self.callbacks.items()):
            try:
                methodwrapper(*args, **kwargs)
            except:
                log.err()

            if onetime:
                del self.callbacks[key]


    def isEmpty(self):
        """
        Return if list of registered callbacks is empty.

        @rtype: C{bool}
        """

        return len(self.callbacks) == 0



class EventDispatcher:
    """
    Event dispatching service.

    The C{EventDispatcher} allows observers to be registered for certain events
    that are dispatched. There are two types of events: XPath events and Named
    events.

    Every dispatch is triggered by calling L{dispatch} with a data object and,
    for named events, the name of the event.

    When an XPath type event is dispatched, the associated object is assumed to
    be an L{Element<twisted.words.xish.domish.Element>} instance, which is
    matched against all registered XPath queries. For every match, the
    respective observer will be called with the data object.

    A named event will simply call each registered observer for that particular
    event name, with the data object. Unlike XPath type events, the data object
    is not restricted to L{Element<twisted.words.xish.domish.Element>}, but can
    be anything.

    When registering observers, the event that is to be observed is specified
    using an L{xpath.XPathQuery} instance or a string. In the latter case, the
    string can also contain the string representation of an XPath expression.
    To distinguish these from named events, each named event should start with
    a special prefix that is stored in C{self.prefix}. It defaults to
    C{//event/}.

    Observers registered using L{addObserver} are persistent: after the
    observer has been triggered by a dispatch, it remains registered for a
    possible next dispatch. If instead L{addOnetimeObserver} was used to
    observe an event, the observer is removed from the list of observers after
    the first observed event.

    Observers can also be prioritized, by providing an optional C{priority}
    parameter to the L{addObserver} and L{addOnetimeObserver} methods. Higher
    priority observers are then called before lower priority observers.

    Finally, observers can be unregistered by using L{removeObserver}.
    """

    def __init__(self, eventprefix="//event/"):
        self.prefix = eventprefix
        self._eventObservers = {}
        self._xpathObservers = {}
        self._dispatchDepth = 0  # Flag indicating levels of dispatching
                                 # in progress
        self._updateQueue = [] # Queued updates for observer ops


    def _getEventAndObservers(self, event):
        if isinstance(event, xpath.XPathQuery):
            # Treat as xpath
            observers = self._xpathObservers
        else:
            if self.prefix == event[:len(self.prefix)]:
                # Treat as event
                observers = self._eventObservers
            else:
                # Treat as xpath
                event = xpath.internQuery(event)
                observers = self._xpathObservers

        return event, observers


    def addOnetimeObserver(self, event, observerfn, priority=0, *args, **kwargs):
        """
        Register a one-time observer for an event.

        Like L{addObserver}, but is only triggered at most once. See there
        for a description of the parameters.
        """
        self._addObserver(True, event, observerfn, priority, *args, **kwargs)


    def addObserver(self, event, observerfn, priority=0, *args, **kwargs):
        """
        Register an observer for an event.

        Each observer will be registered with a certain priority. Higher
        priority observers get called before lower priority observers.

        @param event: Name or XPath query for the event to be monitored.
        @type event: C{str} or L{xpath.XPathQuery}.
        @param observerfn: Function to be called when the specified event
                           has been triggered. This callable takes
                           one parameter: the data object that triggered
                           the event. When specified, the C{*args} and
                           C{**kwargs} parameters to addObserver are being used
                           as additional parameters to the registered observer
                           callable.
        @param priority: (Optional) priority of this observer in relation to
                         other observer that match the same event. Defaults to
                         C{0}.
        @type priority: C{int}
        """
        self._addObserver(False, event, observerfn, priority, *args, **kwargs)


    def _addObserver(self, onetime, event, observerfn, priority, *args, **kwargs):
        # If this is happening in the middle of the dispatch, queue
        # it up for processing after the dispatch completes
        if self._dispatchDepth > 0:
            self._updateQueue.append(lambda:self._addObserver(onetime, event, observerfn, priority, *args, **kwargs))
            return

        event, observers = self._getEventAndObservers(event)

        if priority not in observers:
            cbl = CallbackList()
            observers[priority] = {event: cbl}
        else:
            priorityObservers = observers[priority]
            if event not in priorityObservers:
                cbl = CallbackList()
                observers[priority][event] = cbl
            else:
                cbl = priorityObservers[event]

        cbl.addCallback(onetime, observerfn, *args, **kwargs)


    def removeObserver(self, event, observerfn):
        """
        Remove callable as observer for an event.

        The observer callable is removed for all priority levels for the
        specified event.

        @param event: Event for which the observer callable was registered.
        @type event: C{str} or L{xpath.XPathQuery}
        @param observerfn: Observer callable to be unregistered.
        """

        # If this is happening in the middle of the dispatch, queue
        # it up for processing after the dispatch completes
        if self._dispatchDepth > 0:
            self._updateQueue.append(lambda:self.removeObserver(event, observerfn))
            return

        event, observers = self._getEventAndObservers(event)

        emptyLists = []
        for priority, priorityObservers in iteritems(observers):
            for query, callbacklist in iteritems(priorityObservers):
                if event == query:
                    callbacklist.removeCallback(observerfn)
                    if callbacklist.isEmpty():
                        emptyLists.append((priority, query))

        for priority, query in emptyLists:
            del observers[priority][query]


    def dispatch(self, obj, event=None):
        """
        Dispatch an event.

        When C{event} is L{None}, an XPath type event is triggered, and
        C{obj} is assumed to be an instance of
        L{Element<twisted.words.xish.domish.Element>}. Otherwise, C{event}
        holds the name of the named event being triggered. In the latter case,
        C{obj} can be anything.

        @param obj: The object to be dispatched.
        @param event: Optional event name.
        @type event: C{str}
        """

        foundTarget = False

        self._dispatchDepth += 1

        if event != None:
            # Named event
            observers = self._eventObservers
            match = lambda query, obj: query == event
        else:
            # XPath event
            observers = self._xpathObservers
            match = lambda query, obj: query.matches(obj)

        priorities = list(observers.keys())
        priorities.sort()
        priorities.reverse()

        emptyLists = []
        for priority in priorities:
            for query, callbacklist in iteritems(observers[priority]):
                if match(query, obj):
                    callbacklist.callback(obj)
                    foundTarget = True
                    if callbacklist.isEmpty():
                        emptyLists.append((priority, query))

        for priority, query in emptyLists:
            del observers[priority][query]

        self._dispatchDepth -= 1

        # If this is a dispatch within a dispatch, don't
        # do anything with the updateQueue -- it needs to
        # wait until we've back all the way out of the stack
        if self._dispatchDepth == 0:
            # Deal with pending update operations
            for f in self._updateQueue:
                f()
            self._updateQueue = []

        return foundTarget



class XmlPipe(object):
    """
    XML stream pipe.

    Connects two objects that communicate stanzas through an XML stream like
    interface. Each of the ends of the pipe (sink and source) can be used to
    send XML stanzas to the other side, or add observers to process XML stanzas
    that were sent from the other side.

    XML pipes are usually used in place of regular XML streams that are
    transported over TCP. This is the reason for the use of the names source
    and sink for both ends of the pipe. The source side corresponds with the
    entity that initiated the TCP connection, whereas the sink corresponds with
    the entity that accepts that connection. In this object, though, the source
    and sink are treated equally.

    Unlike Jabber
    L{XmlStream<twisted.words.protocols.jabber.xmlstream.XmlStream>}s, the sink
    and source objects are assumed to represent an eternal connected and
    initialized XML stream. As such, events corresponding to connection,
    disconnection, initialization and stream errors are not dispatched or
    processed.

    @since: 8.2
    @ivar source: Source XML stream.
    @ivar sink: Sink XML stream.
    """

    def __init__(self):
        self.source = EventDispatcher()
        self.sink = EventDispatcher()
        self.source.send = lambda obj: self.sink.dispatch(obj)
        self.sink.send = lambda obj: self.source.dispatch(obj)
