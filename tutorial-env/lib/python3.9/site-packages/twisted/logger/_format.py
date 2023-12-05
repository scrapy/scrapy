# -*- test-case-name: twisted.logger.test.test_format -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tools for formatting logging events.
"""

from collections.abc import Mapping as MappingABC
from datetime import datetime as DateTime
from typing import Any, Callable, Iterator, Mapping, Optional, Union, cast

from constantly import NamedConstant  # type: ignore[import]

from twisted.python._tzhelper import FixedOffsetTimeZone
from twisted.python.failure import Failure
from twisted.python.reflect import safe_repr
from ._flatten import aFormatter, flatFormat
from ._interfaces import LogEvent

timeFormatRFC3339 = "%Y-%m-%dT%H:%M:%S%z"


def formatEvent(event: LogEvent) -> str:
    """
    Formats an event as text, using the format in C{event["log_format"]}.

    This implementation should never raise an exception; if the formatting
    cannot be done, the returned string will describe the event generically so
    that a useful message is emitted regardless.

    @param event: A logging event.

    @return: A formatted string.
    """
    return eventAsText(
        event,
        includeTraceback=False,
        includeTimestamp=False,
        includeSystem=False,
    )


def formatUnformattableEvent(event: LogEvent, error: BaseException) -> str:
    """
    Formats an event as text that describes the event generically and a
    formatting error.

    @param event: A logging event.
    @param error: The formatting error.

    @return: A formatted string.
    """
    try:
        return "Unable to format event {event!r}: {error}".format(
            event=event, error=error
        )
    except BaseException:
        # Yikes, something really nasty happened.
        #
        # Try to recover as much formattable data as possible; hopefully at
        # least the namespace is sane, which will help you find the offending
        # logger.
        failure = Failure()

        text = ", ".join(
            " = ".join((safe_repr(key), safe_repr(value)))
            for key, value in event.items()
        )

        return (
            "MESSAGE LOST: unformattable object logged: {error}\n"
            "Recoverable data: {text}\n"
            "Exception during formatting:\n{failure}".format(
                error=safe_repr(error), failure=failure, text=text
            )
        )


def formatTime(
    when: Optional[float],
    timeFormat: Optional[str] = timeFormatRFC3339,
    default: str = "-",
) -> str:
    """
    Format a timestamp as text.

    Example::

        >>> from time import time
        >>> from twisted.logger import formatTime
        >>>
        >>> t = time()
        >>> formatTime(t)
        u'2013-10-22T14:19:11-0700'
        >>> formatTime(t, timeFormat="%Y/%W")  # Year and week number
        u'2013/42'
        >>>

    @param when: A timestamp.
    @param timeFormat: A time format.
    @param default: Text to return if C{when} or C{timeFormat} is L{None}.

    @return: A formatted time.
    """
    if timeFormat is None or when is None:
        return default
    else:
        tz = FixedOffsetTimeZone.fromLocalTimeStamp(when)
        datetime = DateTime.fromtimestamp(when, tz)
        return str(datetime.strftime(timeFormat))


def formatEventAsClassicLogText(
    event: LogEvent, formatTime: Callable[[Optional[float]], str] = formatTime
) -> Optional[str]:
    """
    Format an event as a line of human-readable text for, e.g. traditional log
    file output.

    The output format is C{"{timeStamp} [{system}] {event}\\n"}, where:

        - C{timeStamp} is computed by calling the given C{formatTime} callable
          on the event's C{"log_time"} value

        - C{system} is the event's C{"log_system"} value, if set, otherwise,
          the C{"log_namespace"} and C{"log_level"}, joined by a C{"#"}.  Each
          defaults to C{"-"} is not set.

        - C{event} is the event, as formatted by L{formatEvent}.

    Example::

        >>> from time import time
        >>> from twisted.logger import formatEventAsClassicLogText
        >>> from twisted.logger import LogLevel
        >>>
        >>> formatEventAsClassicLogText(dict())  # No format, returns None
        >>> formatEventAsClassicLogText(dict(log_format="Hello!"))
        u'- [-#-] Hello!\\n'
        >>> formatEventAsClassicLogText(dict(
        ...     log_format="Hello!",
        ...     log_time=time(),
        ...     log_namespace="my_namespace",
        ...     log_level=LogLevel.info,
        ... ))
        u'2013-10-22T17:30:02-0700 [my_namespace#info] Hello!\\n'
        >>> formatEventAsClassicLogText(dict(
        ...     log_format="Hello!",
        ...     log_time=time(),
        ...     log_system="my_system",
        ... ))
        u'2013-11-11T17:22:06-0800 [my_system] Hello!\\n'
        >>>

    @param event: an event.
    @param formatTime: A time formatter

    @return: A formatted event, or L{None} if no output is appropriate.
    """
    eventText = eventAsText(event, formatTime=formatTime)
    if not eventText:
        return None
    eventText = eventText.replace("\n", "\n\t")
    return eventText + "\n"


class CallMapping(MappingABC):
    """
    Read-only mapping that turns a C{()}-suffix in key names into an invocation
    of the key rather than a lookup of the key.

    Implementation support for L{formatWithCall}.
    """

    def __init__(self, submapping: Mapping[str, Any]) -> None:
        """
        @param submapping: Another read-only mapping which will be used to look
            up items.
        """
        self._submapping = submapping

    def __iter__(self) -> Iterator:
        return iter(self._submapping)

    def __len__(self) -> int:
        return len(self._submapping)

    def __getitem__(self, key: str) -> Any:
        """
        Look up an item in the submapping for this L{CallMapping}, calling it
        if C{key} ends with C{"()"}.
        """
        callit = key.endswith("()")
        realKey = key[:-2] if callit else key
        value = self._submapping[realKey]
        if callit:
            value = value()
        return value


def formatWithCall(formatString: str, mapping: Mapping[str, Any]) -> str:
    """
    Format a string like L{str.format}, but:

        - taking only a name mapping; no positional arguments

        - with the additional syntax that an empty set of parentheses
          correspond to a formatting item that should be called, and its result
          C{str}'d, rather than calling C{str} on the element directly as
          normal.

    For example::

        >>> formatWithCall("{string}, {function()}.",
        ...                dict(string="just a string",
        ...                     function=lambda: "a function"))
        'just a string, a function.'

    @param formatString: A PEP-3101 format string.
    @param mapping: A L{dict}-like object to format.

    @return: The string with formatted values interpolated.
    """
    return str(aFormatter.vformat(formatString, (), CallMapping(mapping)))


def _formatEvent(event: LogEvent) -> str:
    """
    Formats an event as a string, using the format in C{event["log_format"]}.

    This implementation should never raise an exception; if the formatting
    cannot be done, the returned string will describe the event generically so
    that a useful message is emitted regardless.

    @param event: A logging event.

    @return: A formatted string.
    """
    try:
        if "log_flattened" in event:
            return flatFormat(event)

        format = cast(Optional[Union[str, bytes]], event.get("log_format", None))
        if format is None:
            return ""

        # Make sure format is text.
        if isinstance(format, str):
            pass
        elif isinstance(format, bytes):
            format = format.decode("utf-8")
        else:
            raise TypeError(f"Log format must be str, not {format!r}")

        return formatWithCall(format, event)

    except BaseException as e:
        return formatUnformattableEvent(event, e)


def _formatTraceback(failure: Failure) -> str:
    """
    Format a failure traceback, assuming UTF-8 and using a replacement
    strategy for errors.  Every effort is made to provide a usable
    traceback, but should not that not be possible, a message and the
    captured exception are logged.

    @param failure: The failure to retrieve a traceback from.

    @return: The formatted traceback.
    """
    try:
        traceback = failure.getTraceback()
    except BaseException as e:
        traceback = "(UNABLE TO OBTAIN TRACEBACK FROM EVENT):" + str(e)
    return traceback


def _formatSystem(event: LogEvent) -> str:
    """
    Format the system specified in the event in the "log_system" key if set,
    otherwise the C{"log_namespace"} and C{"log_level"}, joined by a C{"#"}.
    Each defaults to C{"-"} is not set.  If formatting fails completely,
    "UNFORMATTABLE" is returned.

    @param event: The event containing the system specification.

    @return: A formatted string representing the "log_system" key.
    """
    system = cast(Optional[str], event.get("log_system", None))
    if system is None:
        level = cast(Optional[NamedConstant], event.get("log_level", None))
        if level is None:
            levelName = "-"
        else:
            levelName = level.name

        system = "{namespace}#{level}".format(
            namespace=cast(str, event.get("log_namespace", "-")),
            level=levelName,
        )
    else:
        try:
            system = str(system)
        except Exception:
            system = "UNFORMATTABLE"
    return system


def eventAsText(
    event: LogEvent,
    includeTraceback: bool = True,
    includeTimestamp: bool = True,
    includeSystem: bool = True,
    formatTime: Callable[[float], str] = formatTime,
) -> str:
    r"""
    Format an event as text.  Optionally, attach timestamp, traceback, and
    system information.

    The full output format is:
    C{"{timeStamp} [{system}] {event}\n{traceback}\n"} where:

        - C{timeStamp} is the event's C{"log_time"} value formatted with
          the provided C{formatTime} callable.

        - C{system} is the event's C{"log_system"} value, if set, otherwise,
          the C{"log_namespace"} and C{"log_level"}, joined by a C{"#"}.  Each
          defaults to C{"-"} is not set.

        - C{event} is the event, as formatted by L{formatEvent}.

        - C{traceback} is the traceback if the event contains a
          C{"log_failure"} key.  In the event the original traceback cannot
          be formatted, a message indicating the failure will be substituted.

    If the event cannot be formatted, and no traceback exists, an empty string
    is returned, even if includeSystem or includeTimestamp are true.

    @param event: A logging event.
    @param includeTraceback: If true and a C{"log_failure"} key exists, append
        a traceback.
    @param includeTimestamp: If true include a formatted timestamp before the
        event.
    @param includeSystem:  If true, include the event's C{"log_system"} value.
    @param formatTime: A time formatter

    @return: A formatted string with specified options.

    @since: Twisted 18.9.0
    """
    eventText = _formatEvent(event)
    if includeTraceback and "log_failure" in event:
        f = event["log_failure"]
        traceback = _formatTraceback(f)
        eventText = "\n".join((eventText, traceback))

    if not eventText:
        return eventText

    timeStamp = ""
    if includeTimestamp:
        timeStamp = "".join([formatTime(cast(float, event.get("log_time", None))), " "])

    system = ""
    if includeSystem:
        system = "".join(["[", _formatSystem(event), "]", " "])

    return "{timeStamp}{system}{eventText}".format(
        timeStamp=timeStamp,
        system=system,
        eventText=eventText,
    )
