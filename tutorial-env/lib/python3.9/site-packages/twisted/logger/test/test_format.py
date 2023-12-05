# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._format}.
"""

from typing import AnyStr, Optional, cast

try:
    from time import tzset

    # We should upgrade to a version of pyflakes that does not require this.
    tzset
except ImportError:
    tzset = None  # type: ignore[assignment]

from twisted.python.failure import Failure
from twisted.python.test.test_tzhelper import addTZCleanup, mktime, setTZ
from twisted.trial import unittest
from twisted.trial.unittest import SkipTest
from .._format import (
    eventAsText,
    formatEvent,
    formatEventAsClassicLogText,
    formatTime,
    formatUnformattableEvent,
    formatWithCall,
)
from .._interfaces import LogEvent
from .._levels import LogLevel


class FormattingTests(unittest.TestCase):
    """
    Tests for basic event formatting functions.
    """

    def test_formatEvent(self) -> None:
        """
        L{formatEvent} will format an event according to several rules:

            - A string with no formatting instructions will be passed straight
              through.

            - PEP 3101 strings will be formatted using the keys and values of
              the event as named fields.

            - PEP 3101 keys ending with C{()} will be treated as instructions
              to call that key (which ought to be a callable) before
              formatting.

        L{formatEvent} will always return L{str}, and if given bytes, will
        always treat its format string as UTF-8 encoded.
        """

        def format(logFormat: AnyStr, **event: object) -> str:
            event["log_format"] = logFormat
            result = formatEvent(event)
            self.assertIs(type(result), str)
            return result

        self.assertEqual("", format(b""))
        self.assertEqual("", format(""))
        self.assertEqual("abc", format("{x}", x="abc"))
        self.assertEqual(
            "no, yes.",
            format("{not_called}, {called()}.", not_called="no", called=lambda: "yes"),
        )
        self.assertEqual("S\xe1nchez", format(b"S\xc3\xa1nchez"))
        self.assertIn("Unable to format event", format(b"S\xe1nchez"))
        maybeResult = format(b"S{a!s}nchez", a=b"\xe1")
        self.assertIn("Sb'\\xe1'nchez", maybeResult)

        xe1 = str(repr(b"\xe1"))
        self.assertIn("S" + xe1 + "nchez", format(b"S{a!r}nchez", a=b"\xe1"))

    def test_formatEventNoFormat(self) -> None:
        """
        Formatting an event with no format.
        """
        event = dict(foo=1, bar=2)
        result = formatEvent(event)

        self.assertEqual("", result)

    def test_formatEventWeirdFormat(self) -> None:
        """
        Formatting an event with a bogus format.
        """
        event = dict(log_format=object(), foo=1, bar=2)
        result = formatEvent(event)

        self.assertIn("Log format must be str", result)
        self.assertIn(repr(event), result)

    def test_formatUnformattableEvent(self) -> None:
        """
        Formatting an event that's just plain out to get us.
        """
        event = dict(log_format="{evil()}", evil=lambda: 1 / 0)
        result = formatEvent(event)

        self.assertIn("Unable to format event", result)
        self.assertIn(repr(event), result)

    def test_formatUnformattableEventWithUnformattableKey(self) -> None:
        """
        Formatting an unformattable event that has an unformattable key.
        """
        event: LogEvent = {
            "log_format": "{evil()}",
            "evil": lambda: 1 / 0,
            cast(str, Unformattable()): "gurk",
        }
        result = formatEvent(event)
        self.assertIn("MESSAGE LOST: unformattable object logged:", result)
        self.assertIn("Recoverable data:", result)
        self.assertIn("Exception during formatting:", result)

    def test_formatUnformattableEventWithUnformattableValue(self) -> None:
        """
        Formatting an unformattable event that has an unformattable value.
        """
        event = dict(
            log_format="{evil()}",
            evil=lambda: 1 / 0,
            gurk=Unformattable(),
        )
        result = formatEvent(event)
        self.assertIn("MESSAGE LOST: unformattable object logged:", result)
        self.assertIn("Recoverable data:", result)
        self.assertIn("Exception during formatting:", result)

    def test_formatUnformattableEventWithUnformattableErrorOMGWillItStop(self) -> None:
        """
        Formatting an unformattable event that has an unformattable value.
        """
        event = dict(
            log_format="{evil()}",
            evil=lambda: 1 / 0,
            recoverable="okay",
        )
        # Call formatUnformattableEvent() directly with a bogus exception.
        result = formatUnformattableEvent(event, cast(BaseException, Unformattable()))
        self.assertIn("MESSAGE LOST: unformattable object logged:", result)
        self.assertIn(repr("recoverable") + " = " + repr("okay"), result)


class TimeFormattingTests(unittest.TestCase):
    """
    Tests for time formatting functions.
    """

    def setUp(self) -> None:
        addTZCleanup(self)

    def test_formatTimeWithDefaultFormat(self) -> None:
        """
        Default time stamp format is RFC 3339 and offset respects the timezone
        as set by the standard C{TZ} environment variable and L{tzset} API.
        """
        if tzset is None:
            raise SkipTest("Platform cannot change timezone; unable to verify offsets.")

        def testForTimeZone(name: str, expectedDST: str, expectedSTD: str) -> None:
            setTZ(name)

            localDST = mktime((2006, 6, 30, 0, 0, 0, 4, 181, 1))
            localSTD = mktime((2007, 1, 31, 0, 0, 0, 2, 31, 0))

            self.assertEqual(formatTime(localDST), expectedDST)
            self.assertEqual(formatTime(localSTD), expectedSTD)

        # UTC
        testForTimeZone(
            "UTC+00",
            "2006-06-30T00:00:00+0000",
            "2007-01-31T00:00:00+0000",
        )

        # West of UTC
        testForTimeZone(
            "EST+05EDT,M4.1.0,M10.5.0",
            "2006-06-30T00:00:00-0400",
            "2007-01-31T00:00:00-0500",
        )

        # East of UTC
        testForTimeZone(
            "CEST-01CEDT,M4.1.0,M10.5.0",
            "2006-06-30T00:00:00+0200",
            "2007-01-31T00:00:00+0100",
        )

        # No DST
        testForTimeZone(
            "CST+06",
            "2006-06-30T00:00:00-0600",
            "2007-01-31T00:00:00-0600",
        )

    def test_formatTimeWithNoTime(self) -> None:
        """
        If C{when} argument is L{None}, we get the default output.
        """
        self.assertEqual(formatTime(None), "-")
        self.assertEqual(formatTime(None, default="!"), "!")

    def test_formatTimeWithNoFormat(self) -> None:
        """
        If C{timeFormat} argument is L{None}, we get the default output.
        """
        t = mktime((2013, 9, 24, 11, 40, 47, 1, 267, 1))
        self.assertEqual(formatTime(t, timeFormat=None), "-")
        self.assertEqual(formatTime(t, timeFormat=None, default="!"), "!")

    def test_formatTimeWithAlternateTimeFormat(self) -> None:
        """
        Alternate time format in output.
        """
        t = mktime((2013, 9, 24, 11, 40, 47, 1, 267, 1))
        self.assertEqual(formatTime(t, timeFormat="%Y/%W"), "2013/38")

    def test_formatTimePercentF(self) -> None:
        """
        "%f" supported in time format.
        """
        self.assertEqual(formatTime(1000000.23456, timeFormat="%f"), "234560")


class ClassicLogFormattingTests(unittest.TestCase):
    """
    Tests for classic text log event formatting functions.
    """

    def test_formatTimeDefault(self) -> None:
        """
        Time is first field.  Default time stamp format is RFC 3339 and offset
        respects the timezone as set by the standard C{TZ} environment variable
        and L{tzset} API.
        """
        if tzset is None:
            raise SkipTest("Platform cannot change timezone; unable to verify offsets.")

        addTZCleanup(self)
        setTZ("UTC+00")

        t = mktime((2013, 9, 24, 11, 40, 47, 1, 267, 1))
        event = dict(log_format="XYZZY", log_time=t)
        self.assertEqual(
            formatEventAsClassicLogText(event),
            "2013-09-24T11:40:47+0000 [-\x23-] XYZZY\n",
        )

    def test_formatTimeCustom(self) -> None:
        """
        Time is first field.  Custom formatting function is an optional
        argument.
        """

        def formatTime(t: Optional[float]) -> str:
            return f"__{t}__"

        event = dict(log_format="XYZZY", log_time=12345)
        self.assertEqual(
            formatEventAsClassicLogText(event, formatTime=formatTime),
            "__12345__ [-\x23-] XYZZY\n",
        )

    def test_formatNamespace(self) -> None:
        """
        Namespace is first part of second field.
        """
        event = dict(log_format="XYZZY", log_namespace="my.namespace")
        self.assertEqual(
            formatEventAsClassicLogText(event),
            "- [my.namespace\x23-] XYZZY\n",
        )

    def test_formatLevel(self) -> None:
        """
        Level is second part of second field.
        """
        event = dict(log_format="XYZZY", log_level=LogLevel.warn)
        self.assertEqual(
            formatEventAsClassicLogText(event),
            "- [-\x23warn] XYZZY\n",
        )

    def test_formatSystem(self) -> None:
        """
        System is second field.
        """
        event = dict(log_format="XYZZY", log_system="S.Y.S.T.E.M.")
        self.assertEqual(
            formatEventAsClassicLogText(event),
            "- [S.Y.S.T.E.M.] XYZZY\n",
        )

    def test_formatSystemRulz(self) -> None:
        """
        System is not supplanted by namespace and level.
        """
        event = dict(
            log_format="XYZZY",
            log_namespace="my.namespace",
            log_level=LogLevel.warn,
            log_system="S.Y.S.T.E.M.",
        )
        self.assertEqual(
            formatEventAsClassicLogText(event),
            "- [S.Y.S.T.E.M.] XYZZY\n",
        )

    def test_formatSystemUnformattable(self) -> None:
        """
        System is not supplanted by namespace and level.
        """
        event = dict(log_format="XYZZY", log_system=Unformattable())
        self.assertEqual(
            formatEventAsClassicLogText(event),
            "- [UNFORMATTABLE] XYZZY\n",
        )

    def test_formatFormat(self) -> None:
        """
        Formatted event is last field.
        """
        event = dict(log_format="id:{id}", id="123")
        self.assertEqual(
            formatEventAsClassicLogText(event),
            "- [-\x23-] id:123\n",
        )

    def test_formatNoFormat(self) -> None:
        """
        No format string.
        """
        event = dict(id="123")
        self.assertIs(formatEventAsClassicLogText(event), None)

    def test_formatEmptyFormat(self) -> None:
        """
        Empty format string.
        """
        event = dict(log_format="", id="123")
        self.assertIs(formatEventAsClassicLogText(event), None)

    def test_formatFormatMultiLine(self) -> None:
        """
        If the formatted event has newlines, indent additional lines.
        """
        event = dict(log_format='XYZZY\nA hollow voice says:\n"Plugh"')
        self.assertEqual(
            formatEventAsClassicLogText(event),
            '- [-\x23-] XYZZY\n\tA hollow voice says:\n\t"Plugh"\n',
        )


class FormatFieldTests(unittest.TestCase):
    """
    Tests for format field functions.
    """

    def test_formatWithCall(self) -> None:
        """
        L{formatWithCall} is an extended version of L{str.format} that
        will interpret a set of parentheses "C{()}" at the end of a format key
        to mean that the format key ought to be I{called} rather than
        stringified.
        """
        self.assertEqual(
            formatWithCall(
                "Hello, {world}. {callme()}.",
                dict(world="earth", callme=lambda: "maybe"),
            ),
            "Hello, earth. maybe.",
        )
        self.assertEqual(
            formatWithCall("Hello, {repr()!r}.", dict(repr=lambda: "repr")),
            "Hello, 'repr'.",
        )


class Unformattable:
    """
    An object that raises an exception from C{__repr__}.
    """

    def __repr__(self) -> str:
        return str(1 / 0)


class CapturedError(Exception):
    """
    A captured error for use in format tests.
    """


class EventAsTextTests(unittest.TestCase):
    """
    Tests for L{eventAsText}, all of which ensure that the
    returned type is UTF-8 decoded text.
    """

    def test_eventWithTraceback(self) -> None:
        """
        An event with a C{log_failure} key will have a traceback appended.
        """
        try:
            raise CapturedError("This is a fake error")
        except CapturedError:
            f = Failure()

        event: LogEvent = {"log_format": "This is a test log message"}
        event["log_failure"] = f
        eventText = eventAsText(event, includeTimestamp=True, includeSystem=False)
        self.assertIn(str(f.getTraceback()), eventText)
        self.assertIn("This is a test log message", eventText)

    def test_formatEmptyEventWithTraceback(self) -> None:
        """
        An event with an empty C{log_format} key appends a traceback from
        the accompanying failure.
        """
        try:
            raise CapturedError("This is a fake error")
        except CapturedError:
            f = Failure()
        event: LogEvent = {"log_format": ""}
        event["log_failure"] = f
        eventText = eventAsText(event, includeTimestamp=True, includeSystem=False)
        self.assertIn(str(f.getTraceback()), eventText)
        self.assertIn("This is a fake error", eventText)

    def test_formatUnformattableWithTraceback(self) -> None:
        """
        An event with an unformattable value in the C{log_format} key still
        has a traceback appended.
        """
        try:
            raise CapturedError("This is a fake error")
        except CapturedError:
            f = Failure()

        event = {
            "log_format": "{evil()}",
            "evil": lambda: 1 / 0,
        }
        event["log_failure"] = f
        eventText = eventAsText(event, includeTimestamp=True, includeSystem=False)
        self.assertIsInstance(eventText, str)
        self.assertIn(str(f.getTraceback()), eventText)
        self.assertIn("This is a fake error", eventText)

    def test_formatUnformattableErrorWithTraceback(self) -> None:
        """
        An event with an unformattable value in the C{log_format} key, that
        throws an exception when __repr__ is invoked still has a traceback
        appended.
        """
        try:
            raise CapturedError("This is a fake error")
        except CapturedError:
            f = Failure()

        event: LogEvent = {
            "log_format": "{evil()}",
            "evil": lambda: 1 / 0,
            cast(str, Unformattable()): "gurk",
        }
        event["log_failure"] = f
        eventText = eventAsText(event, includeTimestamp=True, includeSystem=False)
        self.assertIsInstance(eventText, str)
        self.assertIn("MESSAGE LOST", eventText)
        self.assertIn(str(f.getTraceback()), eventText)
        self.assertIn("This is a fake error", eventText)

    def test_formatEventUnformattableTraceback(self) -> None:
        """
        If a traceback cannot be appended, a message indicating this is true
        is appended.
        """
        event: LogEvent = {"log_format": ""}
        event["log_failure"] = object()
        eventText = eventAsText(event, includeTimestamp=True, includeSystem=False)
        self.assertIsInstance(eventText, str)
        self.assertIn("(UNABLE TO OBTAIN TRACEBACK FROM EVENT)", eventText)

    def test_formatEventNonCritical(self) -> None:
        """
        An event with no C{log_failure} key will not have a traceback appended.
        """
        event: LogEvent = {"log_format": "This is a test log message"}
        eventText = eventAsText(event, includeTimestamp=True, includeSystem=False)
        self.assertIsInstance(eventText, str)
        self.assertIn("This is a test log message", eventText)

    def test_formatTracebackMultibyte(self) -> None:
        """
        An exception message with multibyte characters is properly handled.
        """
        try:
            raise CapturedError("€")
        except CapturedError:
            f = Failure()

        event: LogEvent = {"log_format": "This is a test log message"}
        event["log_failure"] = f
        eventText = eventAsText(event, includeTimestamp=True, includeSystem=False)
        self.assertIn("€", eventText)
        self.assertIn("Traceback", eventText)

    def test_formatTracebackHandlesUTF8DecodeFailure(self) -> None:
        """
        An error raised attempting to decode the UTF still produces a
        valid log message.
        """
        try:
            # 'test' in utf-16
            raise CapturedError(b"\xff\xfet\x00e\x00s\x00t\x00")
        except CapturedError:
            f = Failure()

        event: LogEvent = {"log_format": "This is a test log message"}
        event["log_failure"] = f
        eventText = eventAsText(event, includeTimestamp=True, includeSystem=False)
        self.assertIn("Traceback", eventText)
        self.assertIn(r'CapturedError(b"\xff\xfet\x00e\x00s\x00t\x00")', eventText)

    def test_eventAsTextSystemOnly(self) -> None:
        """
        If includeSystem is specified as the only option no timestamp or
        traceback are printed.
        """
        try:
            raise CapturedError("This is a fake error")
        except CapturedError:
            f = Failure()

        t = mktime((2013, 9, 24, 11, 40, 47, 1, 267, 1))
        event: LogEvent = {
            "log_format": "ABCD",
            "log_system": "fake_system",
            "log_time": t,
        }
        event["log_failure"] = f
        eventText = eventAsText(
            event,
            includeTimestamp=False,
            includeTraceback=False,
            includeSystem=True,
        )
        self.assertEqual(
            eventText,
            "[fake_system] ABCD",
        )

    def test_eventAsTextTimestampOnly(self) -> None:
        """
        If includeTimestamp is specified as the only option no system or
        traceback are printed.
        """
        if tzset is None:
            raise SkipTest("Platform cannot change timezone; unable to verify offsets.")

        addTZCleanup(self)
        setTZ("UTC+00")

        try:
            raise CapturedError("This is a fake error")
        except CapturedError:
            f = Failure()

        t = mktime((2013, 9, 24, 11, 40, 47, 1, 267, 1))
        event: LogEvent = {
            "log_format": "ABCD",
            "log_system": "fake_system",
            "log_time": t,
        }
        event["log_failure"] = f
        eventText = eventAsText(
            event,
            includeTimestamp=True,
            includeTraceback=False,
            includeSystem=False,
        )
        self.assertEqual(
            eventText,
            "2013-09-24T11:40:47+0000 ABCD",
        )

    def test_eventAsTextSystemMissing(self) -> None:
        """
        If includeSystem is specified with a missing system [-#-]
        is used.
        """
        try:
            raise CapturedError("This is a fake error")
        except CapturedError:
            f = Failure()

        t = mktime((2013, 9, 24, 11, 40, 47, 1, 267, 1))
        event: LogEvent = {
            "log_format": "ABCD",
            "log_time": t,
        }
        event["log_failure"] = f
        eventText = eventAsText(
            event,
            includeTimestamp=False,
            includeTraceback=False,
            includeSystem=True,
        )
        self.assertEqual(
            eventText,
            "[-\x23-] ABCD",
        )

    def test_eventAsTextSystemMissingNamespaceAndLevel(self) -> None:
        """
        If includeSystem is specified with a missing system but
        namespace and level are present they are used.
        """
        try:
            raise CapturedError("This is a fake error")
        except CapturedError:
            f = Failure()

        t = mktime((2013, 9, 24, 11, 40, 47, 1, 267, 1))
        event: LogEvent = {
            "log_format": "ABCD",
            "log_time": t,
            "log_level": LogLevel.info,
            "log_namespace": "test",
        }
        event["log_failure"] = f
        eventText = eventAsText(
            event,
            includeTimestamp=False,
            includeTraceback=False,
            includeSystem=True,
        )
        self.assertEqual(
            eventText,
            "[test\x23info] ABCD",
        )

    def test_eventAsTextSystemMissingLevelOnly(self) -> None:
        """
        If includeSystem is specified with a missing system but
        level is present, level is included.
        """
        try:
            raise CapturedError("This is a fake error")
        except CapturedError:
            f = Failure()

        t = mktime((2013, 9, 24, 11, 40, 47, 1, 267, 1))
        event: LogEvent = {
            "log_format": "ABCD",
            "log_time": t,
            "log_level": LogLevel.info,
        }
        event["log_failure"] = f
        eventText = eventAsText(
            event,
            includeTimestamp=False,
            includeTraceback=False,
            includeSystem=True,
        )
        self.assertEqual(
            eventText,
            "[-\x23info] ABCD",
        )
