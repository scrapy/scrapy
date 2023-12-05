# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._logger}.
"""

from typing import List, Optional, Type, cast

from zope.interface import implementer

from constantly import NamedConstant  # type: ignore[import]

from twisted.trial import unittest
from .._format import formatEvent
from .._global import globalLogPublisher
from .._interfaces import ILogObserver, LogEvent
from .._levels import InvalidLogLevelError, LogLevel
from .._logger import Logger


class TestLogger(Logger):
    """
    L{Logger} with an overridden C{emit} method that keeps track of received
    events.
    """

    def emit(
        self, level: NamedConstant, format: Optional[str] = None, **kwargs: object
    ) -> None:
        @implementer(ILogObserver)
        def observer(event: LogEvent) -> None:
            self.event = event

        globalLogPublisher.addObserver(observer)
        try:
            Logger.emit(self, level, format, **kwargs)
        finally:
            globalLogPublisher.removeObserver(observer)

        self.emitted = {
            "level": level,
            "format": format,
            "kwargs": kwargs,
        }


class LogComposedObject:
    """
    A regular object, with a logger attached.
    """

    log = TestLogger()

    def __init__(self, state: Optional[str] = None) -> None:
        self.state = state

    def __str__(self) -> str:
        return f"<LogComposedObject {self.state}>"


class LoggerTests(unittest.TestCase):
    """
    Tests for L{Logger}.
    """

    def test_repr(self) -> None:
        """
        repr() on Logger
        """
        namespace = "bleargh"
        log = Logger(namespace)
        self.assertEqual(repr(log), f"<Logger {repr(namespace)}>")

    def test_namespaceDefault(self) -> None:
        """
        Default namespace is module name.
        """
        log = Logger()
        self.assertEqual(log.namespace, __name__)

    def test_namespaceOMGItsTooHard(self) -> None:
        """
        Default namespace is C{"<unknown>"} when a logger is created from a
        context in which is can't be determined automatically and no namespace
        was specified.
        """
        result: List[Logger] = []
        exec(
            "result.append(Logger())",
            dict(Logger=Logger),
            locals(),
        )
        self.assertEqual(result[0].namespace, "<unknown>")

    def test_namespaceAttribute(self) -> None:
        """
        Default namespace for classes using L{Logger} as a descriptor is the
        class name they were retrieved from.
        """
        obj = LogComposedObject()

        expectedNamespace = "{}.{}".format(
            obj.__module__,
            obj.__class__.__name__,
        )

        self.assertEqual(cast(TestLogger, obj.log).namespace, expectedNamespace)
        self.assertEqual(
            cast(Type[TestLogger], LogComposedObject.log).namespace, expectedNamespace
        )
        self.assertIs(
            cast(Type[TestLogger], LogComposedObject.log).source, LogComposedObject
        )
        self.assertIs(cast(TestLogger, obj.log).source, obj)
        self.assertIsNone(Logger().source)

    def test_descriptorObserver(self) -> None:
        """
        When used as a descriptor, the observer is propagated.
        """
        observed: List[LogEvent] = []

        class MyObject:
            log = Logger(observer=cast(ILogObserver, observed.append))

        MyObject.log.info("hello")
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["log_format"], "hello")

    def test_sourceAvailableForFormatting(self) -> None:
        """
        On instances that have a L{Logger} class attribute, the C{log_source}
        key is available to format strings.
        """
        obj = LogComposedObject("hello")
        log = cast(TestLogger, obj.log)
        log.error("Hello, {log_source}.")

        self.assertIn("log_source", log.event)
        self.assertEqual(log.event["log_source"], obj)

        stuff = formatEvent(log.event)
        self.assertIn("Hello, <LogComposedObject hello>.", stuff)

    def test_basicLogger(self) -> None:
        """
        Test that log levels and messages are emitted correctly for
        Logger.
        """
        log = TestLogger()

        for level in LogLevel.iterconstants():
            format = "This is a {level_name} message"
            message = format.format(level_name=level.name)

            logMethod = getattr(log, level.name)
            logMethod(format, junk=message, level_name=level.name)

            # Ensure that test_emit got called with expected arguments
            self.assertEqual(log.emitted["level"], level)
            self.assertEqual(log.emitted["format"], format)
            self.assertEqual(log.emitted["kwargs"]["junk"], message)

            self.assertTrue(hasattr(log, "event"), "No event observed.")

            self.assertEqual(log.event["log_format"], format)
            self.assertEqual(log.event["log_level"], level)
            self.assertEqual(log.event["log_namespace"], __name__)
            self.assertIsNone(log.event["log_source"])
            self.assertEqual(log.event["junk"], message)

            self.assertEqual(formatEvent(log.event), message)

    def test_sourceOnClass(self) -> None:
        """
        C{log_source} event key refers to the class.
        """

        @implementer(ILogObserver)
        def observer(event: LogEvent) -> None:
            self.assertEqual(event["log_source"], Thingo)

        class Thingo:
            log = TestLogger(observer=observer)

        cast(TestLogger, Thingo.log).info()

    def test_sourceOnInstance(self) -> None:
        """
        C{log_source} event key refers to the instance.
        """

        @implementer(ILogObserver)
        def observer(event: LogEvent) -> None:
            self.assertEqual(event["log_source"], thingo)

        class Thingo:
            log = TestLogger(observer=observer)

        thingo = Thingo()
        cast(TestLogger, thingo.log).info()

    def test_sourceUnbound(self) -> None:
        """
        C{log_source} event key is L{None}.
        """

        @implementer(ILogObserver)
        def observer(event: LogEvent) -> None:
            self.assertIsNone(event["log_source"])

        log = TestLogger(observer=observer)
        log.info()

    def test_defaultFailure(self) -> None:
        """
        Test that log.failure() emits the right data.
        """
        log = TestLogger()
        try:
            raise RuntimeError("baloney!")
        except RuntimeError:
            log.failure("Whoops")

        errors = self.flushLoggedErrors(RuntimeError)
        self.assertEqual(len(errors), 1)

        self.assertEqual(log.emitted["level"], LogLevel.critical)
        self.assertEqual(log.emitted["format"], "Whoops")

    def test_conflictingKwargs(self) -> None:
        """
        Make sure that kwargs conflicting with args don't pass through.
        """
        log = TestLogger()

        log.warn(
            "*",
            log_format="#",
            log_level=LogLevel.error,
            log_namespace="*namespace*",
            log_source="*source*",
        )

        self.assertEqual(log.event["log_format"], "*")
        self.assertEqual(log.event["log_level"], LogLevel.warn)
        self.assertEqual(log.event["log_namespace"], log.namespace)
        self.assertIsNone(log.event["log_source"])

    def test_logInvalidLogLevel(self) -> None:
        """
        Test passing in a bogus log level to C{emit()}.
        """
        log = TestLogger()

        log.emit("*bogus*")

        errors = self.flushLoggedErrors(InvalidLogLevelError)
        self.assertEqual(len(errors), 1)

    def test_trace(self) -> None:
        """
        Tracing keeps track of forwarding to the publisher.
        """

        @implementer(ILogObserver)
        def publisher(event: LogEvent) -> None:
            observer(event)

        @implementer(ILogObserver)
        def observer(event: LogEvent) -> None:
            self.assertEqual(event["log_trace"], [(log, publisher)])

        log = TestLogger(observer=publisher)
        log.info("Hello.", log_trace=[])
