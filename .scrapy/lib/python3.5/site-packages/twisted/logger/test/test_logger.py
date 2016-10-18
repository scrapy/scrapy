# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._logger}.
"""

from twisted.trial import unittest

from .._levels import InvalidLogLevelError
from .._levels import LogLevel
from .._format import formatEvent
from .._logger import Logger
from .._global import globalLogPublisher



class TestLogger(Logger):
    """
    L{Logger} with an overridden C{emit} method that keeps track of received
    events.
    """

    def emit(self, level, format=None, **kwargs):
        def observer(event):
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



class LogComposedObject(object):
    """
    A regular object, with a logger attached.
    """
    log = TestLogger()

    def __init__(self, state=None):
        self.state = state


    def __str__(self):
        return "<LogComposedObject {state}>".format(state=self.state)



class LoggerTests(unittest.TestCase):
    """
    Tests for L{Logger}.
    """

    def test_repr(self):
        """
        repr() on Logger
        """
        namespace = "bleargh"
        log = Logger(namespace)
        self.assertEqual(repr(log), "<Logger {0}>".format(repr(namespace)))


    def test_namespaceDefault(self):
        """
        Default namespace is module name.
        """
        log = Logger()
        self.assertEqual(log.namespace, __name__)


    def test_namespaceAttribute(self):
        """
        Default namespace for classes using L{Logger} as a descriptor is the
        class name they were retrieved from.
        """
        obj = LogComposedObject()
        expectedNamespace = "{0}.{1}".format(
            obj.__module__,
            obj.__class__.__name__,
        )
        self.assertEqual(obj.log.namespace, expectedNamespace)
        self.assertEqual(LogComposedObject.log.namespace, expectedNamespace)
        self.assertIs(LogComposedObject.log.source, LogComposedObject)
        self.assertIs(obj.log.source, obj)
        self.assertIsNone(Logger().source)


    def test_descriptorObserver(self):
        """
        When used as a descriptor, the observer is propagated.
        """
        observed = []

        class MyObject(object):
            log = Logger(observer=observed.append)

        MyObject.log.info("hello")
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]['log_format'], "hello")


    def test_sourceAvailableForFormatting(self):
        """
        On instances that have a L{Logger} class attribute, the C{log_source}
        key is available to format strings.
        """
        obj = LogComposedObject("hello")
        log = obj.log
        log.error("Hello, {log_source}.")

        self.assertIn("log_source", log.event)
        self.assertEqual(log.event["log_source"], obj)

        stuff = formatEvent(log.event)
        self.assertIn("Hello, <LogComposedObject hello>.", stuff)


    def test_basicLogger(self):
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


    def test_sourceOnClass(self):
        """
        C{log_source} event key refers to the class.
        """
        def observer(event):
            self.assertEqual(event["log_source"], Thingo)

        class Thingo(object):
            log = TestLogger(observer=observer)

        Thingo.log.info()


    def test_sourceOnInstance(self):
        """
        C{log_source} event key refers to the instance.
        """
        def observer(event):
            self.assertEqual(event["log_source"], thingo)

        class Thingo(object):
            log = TestLogger(observer=observer)

        thingo = Thingo()
        thingo.log.info()


    def test_sourceUnbound(self):
        """
        C{log_source} event key is L{None}.
        """
        def observer(event):
            self.assertIsNone(event["log_source"])

        log = TestLogger(observer=observer)
        log.info()


    def test_defaultFailure(self):
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


    def test_conflictingKwargs(self):
        """
        Make sure that kwargs conflicting with args don't pass through.
        """
        log = TestLogger()

        log.warn(
            u"*",
            log_format="#",
            log_level=LogLevel.error,
            log_namespace="*namespace*",
            log_source="*source*",
        )

        self.assertEqual(log.event["log_format"], u"*")
        self.assertEqual(log.event["log_level"], LogLevel.warn)
        self.assertEqual(log.event["log_namespace"], log.namespace)
        self.assertIsNone(log.event["log_source"])


    def test_logInvalidLogLevel(self):
        """
        Test passing in a bogus log level to C{emit()}.
        """
        log = TestLogger()

        log.emit("*bogus*")

        errors = self.flushLoggedErrors(InvalidLogLevelError)
        self.assertEqual(len(errors), 1)


    def test_trace(self):
        """
        Tracing keeps track of forwarding to the publisher.
        """
        def publisher(event):
            observer(event)

        def observer(event):
            self.assertEqual(event["log_trace"], [(log, publisher)])

        log = TestLogger(observer=publisher)
        log.info("Hello.", log_trace=[])
