# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._global}.
"""

from __future__ import print_function

import io

from twisted.trial import unittest

from .._file import textFileLogObserver
from .._observer import LogPublisher
from .._logger import Logger
from .._global import LogBeginner
from .._global import MORE_THAN_ONCE_WARNING
from .._levels import LogLevel
from ..test.test_stdlib import nextLine



def compareEvents(test, actualEvents, expectedEvents):
    """
    Compare two sequences of log events, examining only the the keys which are
    present in both.

    @param test: a test case doing the comparison
    @type test: L{unittest.TestCase}

    @param actualEvents: A list of log events that were emitted by a logger.
    @type actualEvents: L{list} of L{dict}

    @param expectedEvents: A list of log events that were expected by a test.
    @type expected: L{list} of L{dict}
    """
    if len(actualEvents) != len(expectedEvents):
        test.assertEqual(actualEvents, expectedEvents)
    allMergedKeys = set()

    for event in expectedEvents:
        allMergedKeys |= set(event.keys())

    def simplify(event):
        copy = event.copy()
        for key in event.keys():
            if key not in allMergedKeys:
                copy.pop(key)
        return copy

    simplifiedActual = [simplify(event) for event in actualEvents]
    test.assertEqual(simplifiedActual, expectedEvents)



class LogBeginnerTests(unittest.TestCase):
    """
    Tests for L{LogBeginner}.
    """

    def setUp(self):
        self.publisher = LogPublisher()
        self.errorStream = io.StringIO()

        class NotSys(object):
            stdout = object()
            stderr = object()

        class NotWarnings(object):
            def __init__(self):
                self.warnings = []

            def showwarning(
                self, message, category, filename, lineno,
                file=None, line=None
            ):
                """
                Emulate warnings.showwarning.

                @param message: A warning message to emit.
                @type message: L{str}

                @param category: A warning category to associate with
                    C{message}.
                @type category: L{warnings.Warning}

                @param filename: A file name for the source code file issuing
                    the warning.
                @type warning: L{str}

                @param lineno: A line number in the source file where the
                    warning was issued.
                @type lineno: L{int}

                @param file: A file to write the warning message to.  If
                    L{None}, write to L{sys.stderr}.
                @type file: file-like object

                @param line: A line of source code to include with the warning
                    message. If L{None}, attempt to read the line from
                    C{filename} and C{lineno}.
                @type line: L{str}
                """
                self.warnings.append(
                    (message, category, filename, lineno, file, line)
                )

        self.sysModule = NotSys()
        self.warningsModule = NotWarnings()
        self.beginner = LogBeginner(
            self.publisher, self.errorStream, self.sysModule,
            self.warningsModule
        )


    def test_beginLoggingToAddObservers(self):
        """
        Test that C{beginLoggingTo()} adds observers.
        """
        event = dict(foo=1, bar=2)

        events1 = []
        events2 = []

        o1 = lambda e: events1.append(e)
        o2 = lambda e: events2.append(e)

        self.beginner.beginLoggingTo((o1, o2))
        self.publisher(event)

        self.assertEqual([event], events1)
        self.assertEqual([event], events2)


    def test_beginLoggingToBufferedEvents(self):
        """
        Test that events are buffered until C{beginLoggingTo()} is
        called.
        """
        event = dict(foo=1, bar=2)

        events1 = []
        events2 = []

        o1 = lambda e: events1.append(e)
        o2 = lambda e: events2.append(e)

        self.publisher(event)  # Before beginLoggingTo; this is buffered
        self.beginner.beginLoggingTo((o1, o2))

        self.assertEqual([event], events1)
        self.assertEqual([event], events2)


    def test_beginLoggingToTwice(self):
        """
        When invoked twice, L{LogBeginner.beginLoggingTo} will emit a log
        message warning the user that they previously began logging, and add
        the new log observers.
        """
        events1 = []
        events2 = []
        fileHandle = io.StringIO()
        textObserver = textFileLogObserver(fileHandle)
        self.publisher(dict(event="prebuffer"))
        firstFilename, firstLine = nextLine()
        self.beginner.beginLoggingTo([events1.append, textObserver])
        self.publisher(dict(event="postbuffer"))
        secondFilename, secondLine = nextLine()
        self.beginner.beginLoggingTo([events2.append, textObserver])
        self.publisher(dict(event="postwarn"))
        warning = dict(
            log_format=MORE_THAN_ONCE_WARNING,
            log_level=LogLevel.warn,
            fileNow=secondFilename, lineNow=secondLine,
            fileThen=firstFilename, lineThen=firstLine
        )

        compareEvents(
            self, events1,
            [
                dict(event="prebuffer"),
                dict(event="postbuffer"),
                warning,
                dict(event="postwarn")
            ]
        )
        compareEvents(self, events2, [warning, dict(event="postwarn")])

        output = fileHandle.getvalue()
        self.assertIn('<{0}:{1}>'.format(firstFilename, firstLine),
                      output)
        self.assertIn('<{0}:{1}>'.format(secondFilename, secondLine),
                      output)


    def test_criticalLogging(self):
        """
        Critical messages will be written as text to the error stream.
        """
        log = Logger(observer=self.publisher)
        log.info("ignore this")
        log.critical("a critical {message}", message="message")
        self.assertEqual(self.errorStream.getvalue(), u"a critical message\n")


    def test_criticalLoggingStops(self):
        """
        Once logging has begun with C{beginLoggingTo}, critical messages are no
        longer written to the output stream.
        """
        log = Logger(observer=self.publisher)
        self.beginner.beginLoggingTo(())
        log.critical("another critical message")
        self.assertEqual(self.errorStream.getvalue(), u"")


    def test_beginLoggingToRedirectStandardIO(self):
        """
        L{LogBeginner.beginLoggingTo} will re-direct the standard output and
        error streams by setting the C{stdio} and C{stderr} attributes on its
        sys module object.
        """
        x = []
        self.beginner.beginLoggingTo([x.append])
        print("Hello, world.", file=self.sysModule.stdout)
        compareEvents(
            self, x, [dict(log_namespace="stdout", log_io="Hello, world.")]
        )
        del x[:]
        print("Error, world.", file=self.sysModule.stderr)
        compareEvents(
            self, x, [dict(log_namespace="stderr", log_io="Error, world.")]
        )


    def test_beginLoggingToDontRedirect(self):
        """
        L{LogBeginner.beginLoggingTo} will leave the existing stdout/stderr in
        place if it has been told not to replace them.
        """
        oldOut = self.sysModule.stdout
        oldErr = self.sysModule.stderr
        self.beginner.beginLoggingTo((), redirectStandardIO=False)
        self.assertIs(self.sysModule.stdout, oldOut)
        self.assertIs(self.sysModule.stderr, oldErr)


    def test_beginLoggingToPreservesEncoding(self):
        """
        When L{LogBeginner.beginLoggingTo} redirects stdout/stderr streams, the
        replacement streams will preserve the encoding of the replaced streams,
        to minimally disrupt any application relying on a specific encoding.
        """

        weird = io.TextIOWrapper(io.BytesIO(), "shift-JIS")
        weirderr = io.TextIOWrapper(io.BytesIO(), "big5")

        self.sysModule.stdout = weird
        self.sysModule.stderr = weirderr

        x = []
        self.beginner.beginLoggingTo([x.append])
        self.assertEqual(self.sysModule.stdout.encoding, "shift-JIS")
        self.assertEqual(self.sysModule.stderr.encoding, "big5")

        self.sysModule.stdout.write(b"\x97\x9B\n")
        self.sysModule.stderr.write(b"\xBC\xFC\n")
        compareEvents(
            self, x, [dict(log_io=u"\u674e"), dict(log_io=u"\u7469")]
        )


    def test_warningsModule(self):
        """
        L{LogBeginner.beginLoggingTo} will redirect the warnings of its
        warnings module into the logging system.
        """
        self.warningsModule.showwarning(
            "a message", DeprecationWarning, __file__, 1
        )
        x = []
        self.beginner.beginLoggingTo([x.append])
        self.warningsModule.showwarning(
            "another message", DeprecationWarning, __file__, 2
        )
        f = io.StringIO()
        self.warningsModule.showwarning(
            "yet another", DeprecationWarning, __file__, 3, file=f
        )
        self.assertEqual(
            self.warningsModule.warnings,
            [
                ("a message", DeprecationWarning, __file__, 1, None, None),
                ("yet another", DeprecationWarning, __file__, 3, f, None),
            ]
        )
        compareEvents(
            self, x,
            [dict(
                warning="another message",
                category=(
                    DeprecationWarning.__module__ + "." +
                    DeprecationWarning.__name__
                ),
                filename=__file__, lineno=2,
            )]
        )
