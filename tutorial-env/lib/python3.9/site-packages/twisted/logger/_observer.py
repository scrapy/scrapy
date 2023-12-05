# -*- test-case-name: twisted.logger.test.test_observer -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Basic log observers.
"""

from typing import Callable, Optional

from zope.interface import implementer

from twisted.python.failure import Failure
from ._interfaces import ILogObserver, LogEvent
from ._logger import Logger

OBSERVER_DISABLED = (
    "Temporarily disabling observer {observer} due to exception: {log_failure}"
)


@implementer(ILogObserver)
class LogPublisher:
    """
    I{ILogObserver} that fans out events to other observers.

    Keeps track of a set of L{ILogObserver} objects and forwards
    events to each.
    """

    def __init__(self, *observers: ILogObserver) -> None:
        self._observers = list(observers)
        self.log = Logger(observer=self)

    def addObserver(self, observer: ILogObserver) -> None:
        """
        Registers an observer with this publisher.

        @param observer: An L{ILogObserver} to add.
        """
        if not callable(observer):
            raise TypeError(f"Observer is not callable: {observer!r}")
        if observer not in self._observers:
            self._observers.append(observer)

    def removeObserver(self, observer: ILogObserver) -> None:
        """
        Unregisters an observer with this publisher.

        @param observer: An L{ILogObserver} to remove.
        """
        try:
            self._observers.remove(observer)
        except ValueError:
            pass

    def __call__(self, event: LogEvent) -> None:
        """
        Forward events to contained observers.
        """
        if "log_trace" not in event:
            trace: Optional[Callable[[ILogObserver], None]] = None

        else:

            def trace(observer: ILogObserver) -> None:
                """
                Add tracing information for an observer.

                @param observer: an observer being forwarded to
                """
                event["log_trace"].append((self, observer))

        brokenObservers = []

        for observer in self._observers:
            if trace is not None:
                trace(observer)

            try:
                observer(event)
            except Exception:
                brokenObservers.append((observer, Failure()))

        for brokenObserver, failure in brokenObservers:
            errorLogger = self._errorLoggerForObserver(brokenObserver)
            errorLogger.failure(
                OBSERVER_DISABLED,
                failure=failure,
                observer=brokenObserver,
            )

    def _errorLoggerForObserver(self, observer: ILogObserver) -> Logger:
        """
        Create an error-logger based on this logger, which does not contain the
        given bad observer.

        @param observer: The observer which previously had an error.

        @return: A L{Logger} without the given observer.
        """
        errorPublisher = LogPublisher(
            *(obs for obs in self._observers if obs is not observer)
        )
        return Logger(observer=errorPublisher)


@implementer(ILogObserver)
def bitbucketLogObserver(event: LogEvent) -> None:
    """
    I{ILogObserver} that does nothing with the events it sees.
    """
