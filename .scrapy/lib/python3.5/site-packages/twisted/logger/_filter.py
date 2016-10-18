# -*- test-case-name: twisted.logger.test.test_filter -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Filtering log observer.
"""

from functools import partial

from zope.interface import Interface, implementer

from twisted.python.constants import NamedConstant, Names
from ._levels import InvalidLogLevelError, LogLevel
from ._observer import ILogObserver



class PredicateResult(Names):
    """
    Predicate results.

    @see: L{LogLevelFilterPredicate}

    @cvar yes: Log the specified event.  When this value is used,
        L{LogLevelFilterPredicate} will always log the message, without
        evaluating other predicates.

    @cvar no: Do not log the specified event.  When this value is used,
        L{LogLevelFilterPredicate} will I{not} log the message, without
        evaluating other predicates.

    @cvar maybe: Do not have an opinion on the event.  When this value is used,
        L{LogLevelFilterPredicate} will consider subsequent predicate results;
        if returned by the last predicate being considered, then the event will
        be logged.
    """
    yes = NamedConstant()
    no = NamedConstant()
    maybe = NamedConstant()



class ILogFilterPredicate(Interface):
    """
    A predicate that determined whether an event should be logged.
    """

    def __call__(event):
        """
        Determine whether an event should be logged.

        @returns: a L{PredicateResult}.
        """



def shouldLogEvent(predicates, event):
    """
    Determine whether an event should be logged, based on the result of
    C{predicates}.

    By default, the result is C{True}; so if there are no predicates,
    everything will be logged.

    If any predicate returns C{yes}, then we will immediately return C{True}.

    If any predicate returns C{no}, then we will immediately return C{False}.

    As predicates return C{maybe}, we keep calling the next predicate until we
    run out, at which point we return C{True}.

    @param predicates: The predicates to use.
    @type predicates: iterable of L{ILogFilterPredicate}

    @param event: An event
    @type event: L{dict}

    @return: True if the message should be forwarded on, C{False} if not.
    @rtype: L{bool}
    """
    for predicate in predicates:
        result = predicate(event)
        if result == PredicateResult.yes:
            return True
        if result == PredicateResult.no:
            return False
        if result == PredicateResult.maybe:
            continue
        raise TypeError("Invalid predicate result: {0!r}".format(result))
    return True



@implementer(ILogObserver)
class FilteringLogObserver(object):
    """
    L{ILogObserver} that wraps another L{ILogObserver}, but filters out events
    based on applying a series of L{ILogFilterPredicate}s.
    """

    def __init__(
        self, observer, predicates,
        negativeObserver=lambda event: None
    ):
        """
        @param observer: An observer to which this observer will forward
            events when C{predictates} yield a positive result.
        @type observer: L{ILogObserver}

        @param predicates: Predicates to apply to events before forwarding to
            the wrapped observer.
        @type predicates: ordered iterable of predicates

        @param negativeObserver: An observer to which this observer will
            forward events when C{predictates} yield a negative result.
        @type negativeObserver: L{ILogObserver}
        """
        self._observer = observer
        self._shouldLogEvent = partial(shouldLogEvent, list(predicates))
        self._negativeObserver = negativeObserver


    def __call__(self, event):
        """
        Forward to next observer if predicate allows it.
        """
        if self._shouldLogEvent(event):
            if "log_trace" in event:
                event["log_trace"].append((self, self.observer))
            self._observer(event)
        else:
            self._negativeObserver(event)



@implementer(ILogFilterPredicate)
class LogLevelFilterPredicate(object):
    """
    L{ILogFilterPredicate} that filters out events with a log level lower than
    the log level for the event's namespace.

    Events that not not have a log level or namespace are also dropped.
    """

    def __init__(self, defaultLogLevel=LogLevel.info):
        """
        @param defaultLogLevel: The default minimum log level.
        @type defaultLogLevel: L{LogLevel}
        """
        self._logLevelsByNamespace = {}
        self.defaultLogLevel = defaultLogLevel
        self.clearLogLevels()


    def logLevelForNamespace(self, namespace):
        """
        Determine an appropriate log level for the given namespace.

        This respects dots in namespaces; for example, if you have previously
        invoked C{setLogLevelForNamespace("mypackage", LogLevel.debug)}, then
        C{logLevelForNamespace("mypackage.subpackage")} will return
        C{LogLevel.debug}.

        @param namespace: A logging namespace, or L{None} for the default
            namespace.
        @type namespace: L{str} (native string)

        @return: The log level for the specified namespace.
        @rtype: L{LogLevel}
        """
        if not namespace:
            return self._logLevelsByNamespace[None]

        if namespace in self._logLevelsByNamespace:
            return self._logLevelsByNamespace[namespace]

        segments = namespace.split(".")
        index = len(segments) - 1

        while index > 0:
            namespace = ".".join(segments[:index])
            if namespace in self._logLevelsByNamespace:
                return self._logLevelsByNamespace[namespace]
            index -= 1

        return self._logLevelsByNamespace[None]


    def setLogLevelForNamespace(self, namespace, level):
        """
        Sets the log level for a logging namespace.

        @param namespace: A logging namespace.
        @type namespace: L{str} (native string)

        @param level: The log level for the given namespace.
        @type level: L{LogLevel}
        """
        if level not in LogLevel.iterconstants():
            raise InvalidLogLevelError(level)

        if namespace:
            self._logLevelsByNamespace[namespace] = level
        else:
            self._logLevelsByNamespace[None] = level


    def clearLogLevels(self):
        """
        Clears all log levels to the default.
        """
        self._logLevelsByNamespace.clear()
        self._logLevelsByNamespace[None] = self.defaultLogLevel


    def __call__(self, event):
        eventLevel     = event.get("log_level", None)
        namespace = event.get("log_namespace", None)
        namespaceLevel = self.logLevelForNamespace(namespace)

        if (
            eventLevel is None or
            namespace is None or
            LogLevel._priorityForLevel(eventLevel) <
            LogLevel._priorityForLevel(namespaceLevel)
        ):
            return PredicateResult.no

        return PredicateResult.maybe
