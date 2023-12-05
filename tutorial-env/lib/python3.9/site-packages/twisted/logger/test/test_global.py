# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._global}.
"""

import io
from typing import IO, Any, List, Optional, TextIO, Tuple, Type, cast

from twisted.python.failure import Failure
from twisted.trial import unittest
from .._file import textFileLogObserver
from .._global import MORE_THAN_ONCE_WARNING, LogBeginner
from .._interfaces import ILogObserver, LogEvent
from .._levels import LogLevel
from .._logger import Logger
from .._observer import LogPublisher
from ..test.test_stdlib import nextLine


def compareEvents(
    test: unittest.TestCase,
    actualEvents: List[LogEvent],
    expectedEvents: List[LogEvent],
) -> None:
    """
    Compare two sequences of log events, examining only the the keys which are
    present in both.

    @param test: a test case doing the comparison
    @param actualEvents: A list of log events that were emitted by a logger.
    @param expectedEvents: A list of log events that were expected by a test.
    """
    if len(actualEvents) != len(expectedEvents):
        test.assertEqual(actualEvents, expectedEvents)
    allMergedKeys = set()

    for event in expectedEvents:
        allMergedKeys |= set(event.keys())

    def simplify(event: LogEvent) -> LogEvent:
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

    def setUp(self) -> None:
        self.publisher = LogPublisher()
        self.errorStream = io.StringIO()

        class NotSys:
            stdout = object()
            stderr = object()

        class NotWarnings:
            def __init__(self) -> None:
                self.warnings: List[
                    Tuple[
                        str, Type[Warning], str, int, Optional[IO[Any]], Optional[int]
                    ]
                ] = []

            def showwarning(
                self,
                message: str,
                category: Type[Warning],
                filename: str,
                lineno: int,
                file: Optional[IO[Any]] = None,
                line: Optional[int] = None,
            ) -> None:
                """
                Emulate warnings.showwarning.

                @param message: A warning message to emit.
                @param category: A warning category to associate with
                    C{message}.
                @param filename: A file name for the source code file issuing
                    the warning.
                @param lineno: A line number in the source file where the
                    warning was issued.
                @param file: A file to write the warning message to.  If
                    L{None}, write to L{sys.stderr}.
                @param line: A line of source code to include with the warning
                    message. If L{None}, attempt to read the line from
                    C{filename} and C{lineno}.
                """
                self.warnings.append((message, category, filename, lineno, file, line))

        self.sysModule = NotSys()
        self.warningsModule = NotWarnings()
        self.beginner = LogBeginner(
            self.publisher, self.errorStream, self.sysModule, self.warningsModule
        )

    def test_beginLoggingToAddObservers(self) -> None:
        """
        Test that C{beginLoggingTo()} adds observers.
        """
        event = dict(foo=1, bar=2)

        events1: List[LogEvent] = []
        events2: List[LogEvent] = []

        o1 = cast(ILogObserver, lambda e: events1.append(e))
        o2 = cast(ILogObserver, lambda e: events2.append(e))

        self.beginner.beginLoggingTo((o1, o2))
        self.publisher(event)

        self.assertEqual([event], events1)
        self.assertEqual([event], events2)

    def test_beginLoggingToBufferedEvents(self) -> None:
        """
        Test that events are buffered until C{beginLoggingTo()} is
        called.
        """
        event = dict(foo=1, bar=2)

        events1: List[LogEvent] = []
        events2: List[LogEvent] = []

        o1 = cast(ILogObserver, lambda e: events1.append(e))
        o2 = cast(ILogObserver, lambda e: events2.append(e))

        self.publisher(event)  # Before beginLoggingTo; this is buffered
        self.beginner.beginLoggingTo((o1, o2))

        self.assertEqual([event], events1)
        self.assertEqual([event], events2)

    def _bufferLimitTest(self, limit: int, beginner: LogBeginner) -> None:
        """
        Verify that when more than C{limit} events are logged to L{LogBeginner},
        only the last C{limit} are replayed by L{LogBeginner.beginLoggingTo}.

        @param limit: The maximum number of events the log beginner should
            buffer.
        @param beginner: The L{LogBeginner} against which to verify.

        @raise: C{self.failureException} if the wrong events are replayed by
            C{beginner}.
        """
        for count in range(limit + 1):
            self.publisher(dict(count=count))
        events: List[LogEvent] = []
        beginner.beginLoggingTo([cast(ILogObserver, events.append)])
        self.assertEqual(
            list(range(1, limit + 1)),
            list(event["count"] for event in events),
        )

    def test_defaultBufferLimit(self) -> None:
        """
        Up to C{LogBeginner._DEFAULT_BUFFER_SIZE} log events are buffered for
        replay by L{LogBeginner.beginLoggingTo}.
        """
        limit = LogBeginner._DEFAULT_BUFFER_SIZE
        self._bufferLimitTest(limit, self.beginner)

    def test_overrideBufferLimit(self) -> None:
        """
        The size of the L{LogBeginner} event buffer can be overridden with the
        C{initialBufferSize} initilizer argument.
        """
        limit = 3
        beginner = LogBeginner(
            self.publisher,
            self.errorStream,
            self.sysModule,
            self.warningsModule,
            initialBufferSize=limit,
        )
        self._bufferLimitTest(limit, beginner)

    def test_beginLoggingToTwice(self) -> None:
        """
        When invoked twice, L{LogBeginner.beginLoggingTo} will emit a log
        message warning the user that they previously began logging, and add
        the new log observers.
        """
        events1: List[LogEvent] = []
        events2: List[LogEvent] = []
        fileHandle = io.StringIO()
        textObserver = textFileLogObserver(fileHandle)
        self.publisher(dict(event="prebuffer"))
        firstFilename, firstLine = nextLine()
        self.beginner.beginLoggingTo([cast(ILogObserver, events1.append), textObserver])
        self.publisher(dict(event="postbuffer"))
        secondFilename, secondLine = nextLine()
        self.beginner.beginLoggingTo([cast(ILogObserver, events2.append), textObserver])
        self.publisher(dict(event="postwarn"))
        warning = dict(
            log_format=MORE_THAN_ONCE_WARNING,
            log_level=LogLevel.warn,
            fileNow=secondFilename,
            lineNow=secondLine,
            fileThen=firstFilename,
            lineThen=firstLine,
        )

        self.maxDiff = None
        compareEvents(
            self,
            events1,
            [
                dict(event="prebuffer"),
                dict(event="postbuffer"),
                warning,
                dict(event="postwarn"),
            ],
        )
        compareEvents(self, events2, [warning, dict(event="postwarn")])

        output = fileHandle.getvalue()
        self.assertIn(f"<{firstFilename}:{firstLine}>", output)
        self.assertIn(f"<{secondFilename}:{secondLine}>", output)

    def test_criticalLogging(self) -> None:
        """
        Critical messages will be written as text to the error stream.
        """
        log = Logger(observer=self.publisher)
        log.info("ignore this")
        log.critical("a critical {message}", message="message")
        self.assertEqual(self.errorStream.getvalue(), "a critical message\n")

    def test_criticalLoggingStops(self) -> None:
        """
        Once logging has begun with C{beginLoggingTo}, critical messages are no
        longer written to the output stream.
        """
        log = Logger(observer=self.publisher)
        self.beginner.beginLoggingTo(())
        log.critical("another critical message")
        self.assertEqual(self.errorStream.getvalue(), "")

    def test_beginLoggingToRedirectStandardIO(self) -> None:
        """
        L{LogBeginner.beginLoggingTo} will re-direct the standard output and
        error streams by setting the C{stdio} and C{stderr} attributes on its
        sys module object.
        """
        events: List[LogEvent] = []
        self.beginner.beginLoggingTo([cast(ILogObserver, events.append)])
        print("Hello, world.", file=cast(TextIO, self.sysModule.stdout))
        compareEvents(
            self, events, [dict(log_namespace="stdout", log_io="Hello, world.")]
        )
        del events[:]
        print("Error, world.", file=cast(TextIO, self.sysModule.stderr))
        compareEvents(
            self, events, [dict(log_namespace="stderr", log_io="Error, world.")]
        )

    def test_beginLoggingToDontRedirect(self) -> None:
        """
        L{LogBeginner.beginLoggingTo} will leave the existing stdout/stderr in
        place if it has been told not to replace them.
        """
        oldOut = self.sysModule.stdout
        oldErr = self.sysModule.stderr
        self.beginner.beginLoggingTo((), redirectStandardIO=False)
        self.assertIs(self.sysModule.stdout, oldOut)
        self.assertIs(self.sysModule.stderr, oldErr)

    def test_beginLoggingToPreservesEncoding(self) -> None:
        """
        When L{LogBeginner.beginLoggingTo} redirects stdout/stderr streams, the
        replacement streams will preserve the encoding of the replaced streams,
        to minimally disrupt any application relying on a specific encoding.
        """

        weird = io.TextIOWrapper(io.BytesIO(), "shift-JIS")
        weirderr = io.TextIOWrapper(io.BytesIO(), "big5")

        self.sysModule.stdout = weird
        self.sysModule.stderr = weirderr

        events: List[LogEvent] = []
        self.beginner.beginLoggingTo([cast(ILogObserver, events.append)])
        stdout = cast(TextIO, self.sysModule.stdout)
        stderr = cast(TextIO, self.sysModule.stderr)
        self.assertEqual(stdout.encoding, "shift-JIS")
        self.assertEqual(stderr.encoding, "big5")

        stdout.write(b"\x97\x9B\n")  # type: ignore[arg-type]
        stderr.write(b"\xBC\xFC\n")  # type: ignore[arg-type]
        compareEvents(self, events, [dict(log_io="\u674e"), dict(log_io="\u7469")])

    def test_warningsModule(self) -> None:
        """
        L{LogBeginner.beginLoggingTo} will redirect the warnings of its
        warnings module into the logging system.
        """
        self.warningsModule.showwarning("a message", DeprecationWarning, __file__, 1)
        events: List[LogEvent] = []
        self.beginner.beginLoggingTo([cast(ILogObserver, events.append)])
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
            ],
        )
        compareEvents(
            self,
            events,
            [
                dict(
                    warning="another message",
                    category=(
                        DeprecationWarning.__module__
                        + "."
                        + DeprecationWarning.__name__
                    ),
                    filename=__file__,
                    lineno=2,
                )
            ],
        )

    def test_failuresAppendTracebacks(self) -> None:
        """
        The string resulting from a logged failure contains a traceback.
        """
        f = Failure(Exception("this is not the behavior you are looking for"))
        log = Logger(observer=self.publisher)
        log.failure("a failure", failure=f)
        msg = self.errorStream.getvalue()
        self.assertIn("a failure", msg)
        self.assertIn("this is not the behavior you are looking for", msg)
        self.assertIn("Traceback", msg)
