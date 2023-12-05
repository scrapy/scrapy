# -*- test-case-name: twisted.logger.test.test_legacy -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Integration with L{twisted.python.log}.
"""

from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from zope.interface import implementer

from ._format import formatEvent
from ._interfaces import ILogObserver, LogEvent
from ._levels import LogLevel
from ._stdlib import StringifiableFromEvent, fromStdlibLogLevelMapping

if TYPE_CHECKING:
    from twisted.python.log import ILogObserver as ILegacyLogObserver


@implementer(ILogObserver)
class LegacyLogObserverWrapper:
    """
    L{ILogObserver} that wraps a L{twisted.python.log.ILogObserver}.

    Received (new-style) events are modified prior to forwarding to
    the legacy observer to ensure compatibility with observers that
    expect legacy events.
    """

    def __init__(self, legacyObserver: "ILegacyLogObserver") -> None:
        """
        @param legacyObserver: a legacy observer to which this observer will
            forward events.
        """
        self.legacyObserver = legacyObserver

    def __repr__(self) -> str:
        return "{self.__class__.__name__}({self.legacyObserver})".format(self=self)

    def __call__(self, event: LogEvent) -> None:
        """
        Forward events to the legacy observer after editing them to
        ensure compatibility.

        @param event: an event
        """

        # The "message" key is required by textFromEventDict()
        if "message" not in event:
            event["message"] = ()

        if "time" not in event:
            event["time"] = event["log_time"]

        if "system" not in event:
            event["system"] = event.get("log_system", "-")

        # Format new style -> old style
        if "format" not in event and event.get("log_format", None) is not None:
            # Create an object that implements __str__() in order to defer the
            # work of formatting until it's needed by a legacy log observer.
            event["format"] = "%(log_legacy)s"
            event["log_legacy"] = StringifiableFromEvent(event.copy())

            # In the old-style system, the 'message' key always holds a tuple
            # of messages. If we find the 'message' key here to not be a
            # tuple, it has been passed as new-style parameter. We drop it
            # here because we render it using the old-style 'format' key,
            # which otherwise doesn't get precedence, and the original event
            # has been copied above.
            if not isinstance(event["message"], tuple):
                event["message"] = ()

        # From log.failure() -> isError blah blah
        if "log_failure" in event:
            if "failure" not in event:
                event["failure"] = event["log_failure"]
            if "isError" not in event:
                event["isError"] = 1
            if "why" not in event:
                event["why"] = formatEvent(event)
        elif "isError" not in event:
            if event["log_level"] in (LogLevel.error, LogLevel.critical):
                event["isError"] = 1
            else:
                event["isError"] = 0

        self.legacyObserver(event)


def publishToNewObserver(
    observer: ILogObserver,
    eventDict: Dict[str, Any],
    textFromEventDict: Callable[[Dict[str, Any]], Optional[str]],
) -> None:
    """
    Publish an old-style (L{twisted.python.log}) event to a new-style
    (L{twisted.logger}) observer.

    @note: It's possible that a new-style event was sent to a
        L{LegacyLogObserverWrapper}, and may now be getting sent back to a
        new-style observer.  In this case, it's already a new-style event,
        adapted to also look like an old-style event, and we don't need to
        tweak it again to be a new-style event, hence this checks for
        already-defined new-style keys.

    @param observer: A new-style observer to handle this event.
    @param eventDict: An L{old-style <twisted.python.log>}, log event.
    @param textFromEventDict: callable that can format an old-style event as a
        string.  Passed here rather than imported to avoid circular dependency.
    """

    if "log_time" not in eventDict:
        eventDict["log_time"] = eventDict["time"]

    if "log_format" not in eventDict:
        text = textFromEventDict(eventDict)
        if text is not None:
            eventDict["log_text"] = text
            eventDict["log_format"] = "{log_text}"

    if "log_level" not in eventDict:
        if "logLevel" in eventDict:
            try:
                level = fromStdlibLogLevelMapping[eventDict["logLevel"]]
            except KeyError:
                level = None
        elif "isError" in eventDict:
            if eventDict["isError"]:
                level = LogLevel.critical
            else:
                level = LogLevel.info
        else:
            level = LogLevel.info

        if level is not None:
            eventDict["log_level"] = level

    if "log_namespace" not in eventDict:
        eventDict["log_namespace"] = "log_legacy"

    if "log_system" not in eventDict and "system" in eventDict:
        eventDict["log_system"] = eventDict["system"]

    observer(eventDict)
