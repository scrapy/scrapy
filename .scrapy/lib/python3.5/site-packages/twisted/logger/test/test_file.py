# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._file}.
"""

from io import StringIO

from zope.interface.verify import verifyObject, BrokenMethodImplementation

from twisted.trial.unittest import TestCase

from twisted.python.failure import Failure
from twisted.python.compat import unicode
from .._observer import ILogObserver
from .._file import FileLogObserver
from .._file import textFileLogObserver



class FileLogObserverTests(TestCase):
    """
    Tests for L{FileLogObserver}.
    """

    def test_interface(self):
        """
        L{FileLogObserver} is an L{ILogObserver}.
        """
        with StringIO() as fileHandle:
            observer = FileLogObserver(fileHandle, lambda e: unicode(e))
            try:
                verifyObject(ILogObserver, observer)
            except BrokenMethodImplementation as e:
                self.fail(e)


    def test_observeWrites(self):
        """
        L{FileLogObserver} writes to the given file when it observes events.
        """
        with StringIO() as fileHandle:
            observer = FileLogObserver(fileHandle, lambda e: unicode(e))
            event = dict(x=1)
            observer(event)
            self.assertEqual(fileHandle.getvalue(), unicode(event))


    def _test_observeWrites(self, what, count):
        """
        Verify that observer performs an expected number of writes when the
        formatter returns a given value.

        @param what: the value for the formatter to return.
        @type what: L{unicode}

        @param count: the expected number of writes.
        @type count: L{int}
        """
        with DummyFile() as fileHandle:
            observer = FileLogObserver(fileHandle, lambda e: what)
            event = dict(x=1)
            observer(event)
            self.assertEqual(fileHandle.writes, count)


    def test_observeWritesNone(self):
        """
        L{FileLogObserver} does not write to the given file when it observes
        events and C{formatEvent} returns L{None}.
        """
        self._test_observeWrites(None, 0)


    def test_observeWritesEmpty(self):
        """
        L{FileLogObserver} does not write to the given file when it observes
        events and C{formatEvent} returns C{u""}.
        """
        self._test_observeWrites(u"", 0)


    def test_observeFlushes(self):
        """
        L{FileLogObserver} calles C{flush()} on the output file when it
        observes an event.
        """
        with DummyFile() as fileHandle:
            observer = FileLogObserver(fileHandle, lambda e: unicode(e))
            event = dict(x=1)
            observer(event)
            self.assertEqual(fileHandle.flushes, 1)


    def test_observeFailure(self):
        """
        If the C{"log_failure"} key exists in an event, the observer appends
        the failure's traceback to the output.
        """
        with StringIO() as fileHandle:
            observer = FileLogObserver(fileHandle, lambda e: unicode(e))

            try:
                1 / 0
            except ZeroDivisionError:
                failure = Failure()

            event = dict(log_failure=failure)
            observer(event)
            output = fileHandle.getvalue()
            self.assertTrue(
                output.startswith("{0}\nTraceback ".format(unicode(event))),
                "Incorrect output:\n{0}".format(output)
            )


    def test_observeFailureThatRaisesInGetTraceback(self):
        """
        If the C{"log_failure"} key exists in an event, and contains an object
        that raises when you call it's C{getTraceback()}, then the observer
        appends a message noting the problem, instead of raising.
        """
        with StringIO() as fileHandle:
            observer = FileLogObserver(fileHandle, lambda e: unicode(e))

            event = dict(log_failure=object())  # object has no getTraceback()
            observer(event)
            output = fileHandle.getvalue()
            expected = (
                "{0}\n(UNABLE TO OBTAIN TRACEBACK FROM EVENT)\n"
                .format(unicode(event))
            )
            self.assertEqual(output, expected)



class TextFileLogObserverTests(TestCase):
    """
    Tests for L{textFileLogObserver}.
    """

    def test_returnsFileLogObserver(self):
        """
        L{textFileLogObserver} returns a L{FileLogObserver}.
        """
        with StringIO() as fileHandle:
            observer = textFileLogObserver(fileHandle)
            self.assertIsInstance(observer, FileLogObserver)


    def test_outFile(self):
        """
        Returned L{FileLogObserver} has the correct outFile.
        """
        with StringIO() as fileHandle:
            observer = textFileLogObserver(fileHandle)
            self.assertIs(observer._outFile, fileHandle)


    def test_timeFormat(self):
        """
        Returned L{FileLogObserver} has the correct outFile.
        """
        with StringIO() as fileHandle:
            observer = textFileLogObserver(fileHandle, timeFormat=u"%f")
            observer(dict(log_format=u"XYZZY", log_time=1.23456))
            self.assertEqual(fileHandle.getvalue(), u"234560 [-#-] XYZZY\n")



class DummyFile(object):
    """
    File that counts writes and flushes.
    """

    def __init__(self):
        self.writes = 0
        self.flushes = 0


    def write(self, data):
        """
        Write data.

        @param data: data
        @type data: L{unicode} or L{bytes}
        """
        self.writes += 1


    def flush(self):
        """
        Flush buffers.
        """
        self.flushes += 1


    def __enter__(self):
        return self


    def __exit__(self, exc_type, exc_value, traceback):
        pass
