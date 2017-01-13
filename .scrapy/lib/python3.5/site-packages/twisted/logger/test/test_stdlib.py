# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._format}.
"""

import sys
from io import BytesIO, TextIOWrapper
import logging as py_logging
from inspect import getsourcefile

from zope.interface.verify import verifyObject, BrokenMethodImplementation

from twisted.python.compat import _PY3, currentframe
from twisted.python.failure import Failure
from twisted.trial import unittest

from .._levels import LogLevel
from .._observer import ILogObserver
from .._stdlib import STDLibLogObserver


def nextLine():
    """
    Retrive the file name and line number immediately after where this function
    is called.

    @return: the file name and line number
    @rtype: 2-L{tuple} of L{str}, L{int}
    """
    caller = currentframe(1)
    return (getsourcefile(sys.modules[caller.f_globals['__name__']]),
            caller.f_lineno + 1)



class STDLibLogObserverTests(unittest.TestCase):
    """
    Tests for L{STDLibLogObserver}.
    """

    def test_interface(self):
        """
        L{STDLibLogObserver} is an L{ILogObserver}.
        """
        observer = STDLibLogObserver()
        try:
            verifyObject(ILogObserver, observer)
        except BrokenMethodImplementation as e:
            self.fail(e)


    def py_logger(self):
        """
        Create a logging object we can use to test with.

        @return: a stdlib-style logger
        @rtype: L{StdlibLoggingContainer}
        """
        logger = StdlibLoggingContainer()
        self.addCleanup(logger.close)
        return logger


    def logEvent(self, *events):
        """
        Send one or more events to Python's logging module, and
        capture the emitted L{logging.LogRecord}s and output stream as
        a string.

        @param events: events
        @type events: L{tuple} of L{dict}

        @return: a tuple: (records, output)
        @rtype: 2-tuple of (L{list} of L{logging.LogRecord}, L{bytes}.)
        """
        pl = self.py_logger()
        observer = STDLibLogObserver(
            # Add 1 to default stack depth to skip *this* frame, since
            # tests will want to know about their own frames.
            stackDepth=STDLibLogObserver.defaultStackDepth + 1
        )
        for event in events:
            observer(event)
        return pl.bufferedHandler.records, pl.outputAsText()


    def test_name(self):
        """
        Logger name.
        """
        records, output = self.logEvent({})

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name, "twisted")


    def test_levels(self):
        """
        Log levels.
        """
        levelMapping = {
            None: py_logging.INFO,  # Default
            LogLevel.debug: py_logging.DEBUG,
            LogLevel.info: py_logging.INFO,
            LogLevel.warn: py_logging.WARNING,
            LogLevel.error: py_logging.ERROR,
            LogLevel.critical: py_logging.CRITICAL,
        }

        # Build a set of events for each log level
        events = []
        for level, pyLevel in levelMapping.items():
            event = {}

            # Set the log level on the event, except for default
            if level is not None:
                event["log_level"] = level

            # Remember the Python log level we expect to see for this
            # event (as an int)
            event["py_levelno"] = int(pyLevel)

            events.append(event)

        records, output = self.logEvent(*events)
        self.assertEqual(len(records), len(levelMapping))

        # Check that each event has the correct level
        for i in range(len(records)):
            self.assertEqual(records[i].levelno, events[i]["py_levelno"])


    def test_callerInfo(self):
        """
        C{pathname}, C{lineno}, C{exc_info}, C{func} is set properly on
        records.
        """
        filename, logLine = nextLine()
        records, output = self.logEvent({})

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].pathname, filename)
        self.assertEqual(records[0].lineno, logLine)
        self.assertIsNone(records[0].exc_info)

        # Attribute "func" is missing from record, which is weird because it's
        # documented.
        # self.assertEqual(records[0].func, "test_callerInfo")


    def test_basicFormat(self):
        """
        Basic formattable event passes the format along correctly.
        """
        event = dict(log_format="Hello, {who}!", who="dude")
        records, output = self.logEvent(event)

        self.assertEqual(len(records), 1)
        self.assertEqual(str(records[0].msg), u"Hello, dude!")
        self.assertEqual(records[0].args, ())


    def test_basicFormatRendered(self):
        """
        Basic formattable event renders correctly.
        """
        event = dict(log_format="Hello, {who}!", who="dude")
        records, output = self.logEvent(event)

        self.assertEqual(len(records), 1)
        self.assertTrue(output.endswith(u":Hello, dude!\n"),
                        repr(output))


    def test_noFormat(self):
        """
        Event with no format.
        """
        records, output = self.logEvent({})

        self.assertEqual(len(records), 1)
        self.assertEqual(str(records[0].msg), "")


    def test_failure(self):
        """
        An event with a failure logs the failure details as well.
        """
        def failing_func():
            1 / 0
        try:
            failing_func()
        except ZeroDivisionError:
            failure = Failure()
        event = dict(log_format='Hi mom', who='me', log_failure=failure)
        records, output = self.logEvent(event)
        self.assertEqual(len(records), 1)
        self.assertIn(u'Hi mom', output)
        self.assertIn(u'in failing_func', output)
        self.assertIn(u'ZeroDivisionError', output)


    def test_cleanedFailure(self):
        """
        A cleaned Failure object has a fake traceback object; make sure that
        logging such a failure still results in the exception details being
        logged.
        """
        def failing_func():
            1 / 0
        try:
            failing_func()
        except ZeroDivisionError:
            failure = Failure()
        failure.cleanFailure()
        event = dict(log_format='Hi mom', who='me', log_failure=failure)
        records, output = self.logEvent(event)
        self.assertEqual(len(records), 1)
        self.assertIn(u'Hi mom', output)
        self.assertIn(u'in failing_func', output)
        self.assertIn(u'ZeroDivisionError', output)



class StdlibLoggingContainer(object):
    """
    Continer for a test configuration of stdlib logging objects.
    """

    def __init__(self):
        self.rootLogger = py_logging.getLogger("")

        self.originalLevel = self.rootLogger.getEffectiveLevel()
        self.rootLogger.setLevel(py_logging.DEBUG)

        self.bufferedHandler = BufferedHandler()
        self.rootLogger.addHandler(self.bufferedHandler)

        self.streamHandler, self.output = handlerAndBytesIO()
        self.rootLogger.addHandler(self.streamHandler)


    def close(self):
        """
        Close the logger.
        """
        self.rootLogger.setLevel(self.originalLevel)
        self.rootLogger.removeHandler(self.bufferedHandler)
        self.rootLogger.removeHandler(self.streamHandler)
        self.streamHandler.close()
        self.output.close()


    def outputAsText(self):
        """
        Get the output to the underlying stream as text.

        @return: the output text
        @rtype: L{unicode}
        """
        return self.output.getvalue().decode("utf-8")



def handlerAndBytesIO():
    """
    Construct a 2-tuple of C{(StreamHandler, BytesIO)} for testing interaction
    with the 'logging' module.

    @return: handler and io object
    @rtype: tuple of L{StreamHandler} and L{io.BytesIO}
    """
    output = BytesIO()
    stream = output
    template = py_logging.BASIC_FORMAT
    if _PY3:
        stream = TextIOWrapper(output, encoding="utf-8")
    formatter = py_logging.Formatter(template)
    handler = py_logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    return handler, output



class BufferedHandler(py_logging.Handler):
    """
    A L{py_logging.Handler} that remembers all logged records in a list.
    """

    def __init__(self):
        """
        Initialize this L{BufferedHandler}.
        """
        py_logging.Handler.__init__(self)
        self.records = []


    def emit(self, record):
        """
        Remember the record.
        """
        self.records.append(record)
