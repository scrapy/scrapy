# -*- test-case-name: twisted.logger.test.test_filter -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Filtering log observer.
"""

from functools import partial
from typing import Dict, Iterable

from zope.interface import Interface, implementer

from constantly import NamedConstant, Names  # type: ignore[import]

from ._interfaces import ILogObserver, LogEvent
from ._levels import InvalidLogLevelError, LogLevel
from ._observer import bitbucketLogObserver


class PredicateResult(Names):
    """
    Predicate results.

    @see: L{LogLevelFilterPredicate}

    @cvar yes: Log the specified event.  When this value is used,
        L{FilteringLogObserver} will always log the message, without
        evaluating other predicates.

    @cvar no: Do not log the specified event.  When this value is used,
        L{FilteringLogObserver} will I{not} log the message, without
        evaluating other predicates.

    @cvar maybe: Do not have an opinion on the event.  When this value is used,
        L{FilteringLogObserver} will consider subsequent predicate results;
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

    def __call__(event: LogEvent) -> NamedConstant:
        """
        Determine whether an event should be logged.

        @returns: a L{PredicateResult}.
        """


def shouldLogEvent(predicates: Iterable[ILogFilterPredicate], event: LogEvent) -> bool:
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
    @param event: An event

    @return: True if the message should be forwarded on, C{False} if not.
    """
    for predicate in predicates:
        result = predicate(event)
        if result == PredicateResult.yes:
            return True
        if result == PredicateResult.no:
            return False
        if result == PredicateResult.maybe:
            continue
        raise TypeError(f"Invalid predicate result: {result!r}")
    return True


@implementer(ILogObserver)
class FilteringLogObserver:
    """
    L{ILogObserver} that wraps another L{ILogObserver}, but filters out events
    based on applying a series of L{ILogFilterPredicate}s.
    """

    def __init__(
        self,
        observer: ILogObserver,
        predicates: Iterable[ILogFilterPredicate],
        negativeObserver: ILogObserver = bitbucketLogObserver,
    ) -> None:
        """
        @param observer: An observer to which this observer will forward
            events when C{predictates} yield a positive result.
        @param predicates: Predicates to apply to events before forwarding to
            the wrapped observer.
        @param negativeObserver: An observer to which this observer will
            forward events when C{predictates} yield a negative result.
        """
        self._observer = observer
        self._shouldLogEvent = partial(shouldLogEvent, list(predicates))
        self._negativeObserver = negativeObserver

    def __call__(self, event: LogEvent) -> None:
        """
        Forward to next observer if predicate allows it.
        """
        if self._shouldLogEvent(event):
            if "log_trace" in event:
                event["log_trace"].append((self, self._observer))
            self._observer(event)
        else:
            self._negativeObserver(event)


@implementer(ILogFilterPredicate)
class LogLevelFilterPredicate:
    """
    L{ILogFilterPredicate} that filters out events with a log level lower than
    the log level for the event's namespace.

    Events that not not have a log level or namespace are also dropped.
    """

    def __init__(self, defaultLogLevel: NamedConstant = LogLevel.info) -> None:
        """
        @param defaultLogLevel: The default minimum log level.
        """
        self._logLevelsByNamespace: Dict[str, NamedConstant] = {}
        self.defaultLogLevel = defaultLogLevel
        self.clearLogLevels()

    def logLevelForNamespace(self, namespace: str) -> NamedConstant:
        """
        Determine an appropriate log level for the given namespace.

        This respects dots in namespaces; for example, if you have previously
        invoked C{setLogLevelForNamespace("mypackage", LogLevel.debug)}, then
        C{logLevelForNamespace("mypackage.subpackage")} will return
        C{LogLevel.debug}.

        @param namespace: A logging namespace.  Use C{""} for the default
            namespace.

        @return: The log level for the specified namespace.
        """
        if not namespace:
            return self._logLevelsByNamespace[""]

        if namespace in self._logLevelsByNamespace:
            return self._logLevelsByNamespace[namespace]

        segments = namespace.split(".")
        index = len(segments) - 1

        while index > 0:
            namespace = ".".join(segments[:index])
            if namespace in self._logLevelsByNamespace:
                return self._logLevelsByNamespace[namespace]
            index -= 1

        return self._logLevelsByNamespace[""]

    def setLogLevelForNamespace(self, namespace: str, level: NamedConstant) -> None:
        """
        Sets the log level for a logging namespace.

        @param namespace: A logging namespace.
        @param level: The log level for the given namespace.
        """
        if level not in LogLevel.iterconstants():
            raise InvalidLogLevelError(level)

        if namespace:
            self._logLevelsByNamespace[namespace] = level
        else:
            self._logLevelsByNamespace[""] = level

    def clearLogLevels(self) -> None:
        """
        Clears all log levels to the default.
        """
        self._logLevelsByNamespace.clear()
        self._logLevelsByNamespace[""] = self.defaultLogLevel

    def __call__(self, event: LogEvent) -> NamedConstant:
        eventLevel = event.get("log_level", None)
        if eventLevel is None:
            return PredicateResult.no

        namespace = event.get("log_namespace", "")
        if not namespace:
            return PredicateResult.no

        namespaceLevel = self.logLevelForNamespace(namespace)
        if eventLevel < namespaceLevel:
            return PredicateResult.no

        return PredicateResult.maybe
