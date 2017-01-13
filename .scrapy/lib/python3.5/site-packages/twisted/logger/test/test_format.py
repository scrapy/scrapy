# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._format}.
"""

from twisted.python.test.test_tzhelper import mktime, addTZCleanup, setTZ

try:
    from time import tzset
    # We should upgrade to a version of pyflakes that does not require this.
    tzset
except ImportError:
    tzset = None

from twisted.trial import unittest
from twisted.trial.unittest import SkipTest

from twisted.python.compat import _PY3, unicode
from .._levels import LogLevel
from .._format import (
    formatEvent, formatUnformattableEvent, formatTime,
    formatEventAsClassicLogText, formatWithCall,
)



class FormattingTests(unittest.TestCase):
    """
    Tests for basic event formatting functions.
    """

    def test_formatEvent(self):
        """
        L{formatEvent} will format an event according to several rules:

            - A string with no formatting instructions will be passed straight
              through.

            - PEP 3101 strings will be formatted using the keys and values of
              the event as named fields.

            - PEP 3101 keys ending with C{()} will be treated as instructions
              to call that key (which ought to be a callable) before
              formatting.

        L{formatEvent} will always return L{unicode}, and if given bytes, will
        always treat its format string as UTF-8 encoded.
        """
        def format(logFormat, **event):
            event["log_format"] = logFormat
            result = formatEvent(event)
            self.assertIs(type(result), unicode)
            return result

        self.assertEqual(u"", format(b""))
        self.assertEqual(u"", format(u""))
        self.assertEqual(u"abc", format("{x}", x="abc"))
        self.assertEqual(
            u"no, yes.",
            format(
                "{not_called}, {called()}.",
                not_called="no", called=lambda: "yes"
            )
        )
        self.assertEqual(u"S\xe1nchez", format(b"S\xc3\xa1nchez"))
        badResult = format(b"S\xe1nchez")
        self.assertIn(u"Unable to format event", badResult)
        maybeResult = format(b"S{a!s}nchez", a=b"\xe1")
        # The behavior of unicode.format("{x}", x=bytes) differs on py2 and
        # py3.  Perhaps we should make our modified formatting more consistent
        # than this? -glyph
        if not _PY3:
            self.assertIn(u"Unable to format event", maybeResult)
        else:
            self.assertIn(u"Sb'\\xe1'nchez", maybeResult)

        xe1 = unicode(repr(b"\xe1"))
        self.assertIn(u"S" + xe1 + "nchez", format(b"S{a!r}nchez", a=b"\xe1"))


    def test_formatEventNoFormat(self):
        """
        Formatting an event with no format.
        """
        event = dict(foo=1, bar=2)
        result = formatEvent(event)

        self.assertEqual(u"", result)


    def test_formatEventWeirdFormat(self):
        """
        Formatting an event with a bogus format.
        """
        event = dict(log_format=object(), foo=1, bar=2)
        result = formatEvent(event)

        self.assertIn("Log format must be unicode or bytes", result)
        self.assertIn(repr(event), result)


    def test_formatUnformattableEvent(self):
        """
        Formatting an event that's just plain out to get us.
        """
        event = dict(log_format="{evil()}", evil=lambda: 1 / 0)
        result = formatEvent(event)

        self.assertIn("Unable to format event", result)
        self.assertIn(repr(event), result)


    def test_formatUnformattableEventWithUnformattableKey(self):
        """
        Formatting an unformattable event that has an unformattable key.
        """
        event = {
            "log_format": "{evil()}",
            "evil": lambda: 1 / 0,
            Unformattable(): "gurk",
        }
        result = formatEvent(event)
        self.assertIn("MESSAGE LOST: unformattable object logged:", result)
        self.assertIn("Recoverable data:", result)
        self.assertIn("Exception during formatting:", result)


    def test_formatUnformattableEventWithUnformattableValue(self):
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


    def test_formatUnformattableEventWithUnformattableErrorOMGWillItStop(self):
        """
        Formatting an unformattable event that has an unformattable value.
        """
        event = dict(
            log_format="{evil()}",
            evil=lambda: 1 / 0,
            recoverable="okay",
        )
        # Call formatUnformattableEvent() directly with a bogus exception.
        result = formatUnformattableEvent(event, Unformattable())
        self.assertIn("MESSAGE LOST: unformattable object logged:", result)
        self.assertIn(repr("recoverable") + " = " + repr("okay"), result)



class TimeFormattingTests(unittest.TestCase):
    """
    Tests for time formatting functions.
    """

    def setUp(self):
        addTZCleanup(self)


    def test_formatTimeWithDefaultFormat(self):
        """
        Default time stamp format is RFC 3339 and offset respects the timezone
        as set by the standard C{TZ} environment variable and L{tzset} API.
        """
        if tzset is None:
            raise SkipTest(
                "Platform cannot change timezone; unable to verify offsets."
            )

        def testForTimeZone(name, expectedDST, expectedSTD):
            setTZ(name)

            localDST = mktime((2006, 6, 30, 0, 0, 0, 4, 181, 1))
            localSTD = mktime((2007, 1, 31, 0, 0, 0, 2, 31, 0))

            self.assertEqual(formatTime(localDST), expectedDST)
            self.assertEqual(formatTime(localSTD), expectedSTD)

        # UTC
        testForTimeZone(
            "UTC+00",
            u"2006-06-30T00:00:00+0000",
            u"2007-01-31T00:00:00+0000",
        )

        # West of UTC
        testForTimeZone(
            "EST+05EDT,M4.1.0,M10.5.0",
            u"2006-06-30T00:00:00-0400",
            u"2007-01-31T00:00:00-0500",
        )

        # East of UTC
        testForTimeZone(
            "CEST-01CEDT,M4.1.0,M10.5.0",
            u"2006-06-30T00:00:00+0200",
            u"2007-01-31T00:00:00+0100",
        )

        # No DST
        testForTimeZone(
            "CST+06",
            u"2006-06-30T00:00:00-0600",
            u"2007-01-31T00:00:00-0600",
        )


    def test_formatTimeWithNoTime(self):
        """
        If C{when} argument is L{None}, we get the default output.
        """
        self.assertEqual(formatTime(None), u"-")
        self.assertEqual(formatTime(None, default=u"!"), u"!")


    def test_formatTimeWithNoFormat(self):
        """
        If C{timeFormat} argument is L{None}, we get the default output.
        """
        t = mktime((2013, 9, 24, 11, 40, 47, 1, 267, 1))
        self.assertEqual(formatTime(t, timeFormat=None), u"-")
        self.assertEqual(formatTime(t, timeFormat=None, default=u"!"), u"!")


    def test_formatTimeWithAlternateTimeFormat(self):
        """
        Alternate time format in output.
        """
        t = mktime((2013, 9, 24, 11, 40, 47, 1, 267, 1))
        self.assertEqual(formatTime(t, timeFormat="%Y/%W"), u"2013/38")


    def test_formatTimePercentF(self):
        """
        "%f" supported in time format.
        """
        self.assertEqual(formatTime(1.23456, timeFormat="%f"), u"234560")



class ClassicLogFormattingTests(unittest.TestCase):
    """
    Tests for classic text log event formatting functions.
    """

    def test_formatTimeDefault(self):
        """
        Time is first field.  Default time stamp format is RFC 3339 and offset
        respects the timezone as set by the standard C{TZ} environment variable
        and L{tzset} API.
        """
        if tzset is None:
            raise SkipTest(
                "Platform cannot change timezone; unable to verify offsets."
            )

        addTZCleanup(self)
        setTZ("UTC+00")

        t = mktime((2013, 9, 24, 11, 40, 47, 1, 267, 1))
        event = dict(log_format=u"XYZZY", log_time=t)
        self.assertEqual(
            formatEventAsClassicLogText(event),
            u"2013-09-24T11:40:47+0000 [-#-] XYZZY\n",
        )


    def test_formatTimeCustom(self):
        """
        Time is first field.  Custom formatting function is an optional
        argument.
        """
        formatTime = lambda t: u"__{0}__".format(t)
        event = dict(log_format=u"XYZZY", log_time=12345)
        self.assertEqual(
            formatEventAsClassicLogText(event, formatTime=formatTime),
            u"__12345__ [-#-] XYZZY\n",
        )


    def test_formatNamespace(self):
        """
        Namespace is first part of second field.
        """
        event = dict(log_format=u"XYZZY", log_namespace="my.namespace")
        self.assertEqual(
            formatEventAsClassicLogText(event),
            u"- [my.namespace#-] XYZZY\n",
        )


    def test_formatLevel(self):
        """
        Level is second part of second field.
        """
        event = dict(log_format=u"XYZZY", log_level=LogLevel.warn)
        self.assertEqual(
            formatEventAsClassicLogText(event),
            u"- [-#warn] XYZZY\n",
        )


    def test_formatSystem(self):
        """
        System is second field.
        """
        event = dict(log_format=u"XYZZY", log_system=u"S.Y.S.T.E.M.")
        self.assertEqual(
            formatEventAsClassicLogText(event),
            u"- [S.Y.S.T.E.M.] XYZZY\n",
        )


    def test_formatSystemRulz(self):
        """
        System is not supplanted by namespace and level.
        """
        event = dict(
            log_format=u"XYZZY",
            log_namespace="my.namespace",
            log_level=LogLevel.warn,
            log_system=u"S.Y.S.T.E.M.",
        )
        self.assertEqual(
            formatEventAsClassicLogText(event),
            u"- [S.Y.S.T.E.M.] XYZZY\n",
        )


    def test_formatSystemUnformattable(self):
        """
        System is not supplanted by namespace and level.
        """
        event = dict(log_format=u"XYZZY", log_system=Unformattable())
        self.assertEqual(
            formatEventAsClassicLogText(event),
            u"- [UNFORMATTABLE] XYZZY\n",
        )


    def test_formatFormat(self):
        """
        Formatted event is last field.
        """
        event = dict(log_format=u"id:{id}", id="123")
        self.assertEqual(
            formatEventAsClassicLogText(event),
            u"- [-#-] id:123\n",
        )


    def test_formatNoFormat(self):
        """
        No format string.
        """
        event = dict(id="123")
        self.assertIs(
            formatEventAsClassicLogText(event),
            None
        )


    def test_formatEmptyFormat(self):
        """
        Empty format string.
        """
        event = dict(log_format="", id="123")
        self.assertIs(
            formatEventAsClassicLogText(event),
            None
        )


    def test_formatFormatMultiLine(self):
        """
        If the formatted event has newlines, indent additional lines.
        """
        event = dict(log_format=u'XYZZY\nA hollow voice says:\n"Plugh"')
        self.assertEqual(
            formatEventAsClassicLogText(event),
            u'- [-#-] XYZZY\n\tA hollow voice says:\n\t"Plugh"\n',
        )



class FormatFieldTests(unittest.TestCase):
    """
    Tests for format field functions.
    """

    def test_formatWithCall(self):
        """
        L{formatWithCall} is an extended version of L{unicode.format} that
        will interpret a set of parentheses "C{()}" at the end of a format key
        to mean that the format key ought to be I{called} rather than
        stringified.
        """
        self.assertEqual(
            formatWithCall(
                u"Hello, {world}. {callme()}.",
                dict(world="earth", callme=lambda: "maybe")
            ),
            "Hello, earth. maybe."
        )
        self.assertEqual(
            formatWithCall(
                u"Hello, {repr()!r}.",
                dict(repr=lambda: "repr")
            ),
            "Hello, 'repr'."
        )



class Unformattable(object):
    """
    An object that raises an exception from C{__repr__}.
    """

    def __repr__(self):
        return str(1 / 0)
