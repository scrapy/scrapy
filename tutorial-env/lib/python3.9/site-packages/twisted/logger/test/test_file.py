# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._file}.
"""

from io import StringIO
from types import TracebackType
from typing import IO, Any, AnyStr, Optional, Type, cast

from zope.interface.exceptions import BrokenMethodImplementation
from zope.interface.verify import verifyObject

from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase
from .._file import FileLogObserver, textFileLogObserver
from .._interfaces import ILogObserver


class FileLogObserverTests(TestCase):
    """
    Tests for L{FileLogObserver}.
    """

    def test_interface(self) -> None:
        """
        L{FileLogObserver} is an L{ILogObserver}.
        """
        with StringIO() as fileHandle:
            observer = FileLogObserver(fileHandle, lambda e: str(e))
            try:
                verifyObject(ILogObserver, observer)
            except BrokenMethodImplementation as e:
                self.fail(e)

    def test_observeWrites(self) -> None:
        """
        L{FileLogObserver} writes to the given file when it observes events.
        """
        with StringIO() as fileHandle:
            observer = FileLogObserver(fileHandle, lambda e: str(e))
            event = dict(x=1)
            observer(event)
            self.assertEqual(fileHandle.getvalue(), str(event))

    def _test_observeWrites(self, what: Optional[str], count: int) -> None:
        """
        Verify that observer performs an expected number of writes when the
        formatter returns a given value.

        @param what: the value for the formatter to return.
        @param count: the expected number of writes.
        """
        with DummyFile() as fileHandle:
            observer = FileLogObserver(cast(IO[Any], fileHandle), lambda e: what)
            event = dict(x=1)
            observer(event)
            self.assertEqual(fileHandle.writes, count)

    def test_observeWritesNone(self) -> None:
        """
        L{FileLogObserver} does not write to the given file when it observes
        events and C{formatEvent} returns L{None}.
        """
        self._test_observeWrites(None, 0)

    def test_observeWritesEmpty(self) -> None:
        """
        L{FileLogObserver} does not write to the given file when it observes
        events and C{formatEvent} returns C{""}.
        """
        self._test_observeWrites("", 0)

    def test_observeFlushes(self) -> None:
        """
        L{FileLogObserver} calles C{flush()} on the output file when it
        observes an event.
        """
        with DummyFile() as fileHandle:
            observer = FileLogObserver(cast(IO[Any], fileHandle), lambda e: str(e))
            event = dict(x=1)
            observer(event)
            self.assertEqual(fileHandle.flushes, 1)


class TextFileLogObserverTests(TestCase):
    """
    Tests for L{textFileLogObserver}.
    """

    def test_returnsFileLogObserver(self) -> None:
        """
        L{textFileLogObserver} returns a L{FileLogObserver}.
        """
        with StringIO() as fileHandle:
            observer = textFileLogObserver(fileHandle)
            self.assertIsInstance(observer, FileLogObserver)

    def test_outFile(self) -> None:
        """
        Returned L{FileLogObserver} has the correct outFile.
        """
        with StringIO() as fileHandle:
            observer = textFileLogObserver(fileHandle)
            self.assertIs(observer._outFile, fileHandle)

    def test_timeFormat(self) -> None:
        """
        Returned L{FileLogObserver} has the correct outFile.
        """
        with StringIO() as fileHandle:
            observer = textFileLogObserver(fileHandle, timeFormat="%f")
            observer(dict(log_format="XYZZY", log_time=112345.6))
            self.assertEqual(fileHandle.getvalue(), "600000 [-#-] XYZZY\n")

    def test_observeFailure(self) -> None:
        """
        If the C{"log_failure"} key exists in an event, the observer appends
        the failure's traceback to the output.
        """
        with StringIO() as fileHandle:
            observer = textFileLogObserver(fileHandle)

            try:
                1 / 0
            except ZeroDivisionError:
                failure = Failure()

            event = dict(log_failure=failure)
            observer(event)
            output = fileHandle.getvalue()
            self.assertTrue(
                output.split("\n")[1].startswith("\tTraceback "), msg=repr(output)
            )

    def test_observeFailureThatRaisesInGetTraceback(self) -> None:
        """
        If the C{"log_failure"} key exists in an event, and contains an object
        that raises when you call its C{getTraceback()}, then the observer
        appends a message noting the problem, instead of raising.
        """
        with StringIO() as fileHandle:
            observer = textFileLogObserver(fileHandle)
            event = dict(log_failure=object())  # object has no getTraceback()
            observer(event)
            output = fileHandle.getvalue()
            expected = "(UNABLE TO OBTAIN TRACEBACK FROM EVENT)"
            self.assertIn(expected, output)


class DummyFile:
    """
    File that counts writes and flushes.
    """

    def __init__(self) -> None:
        self.writes = 0
        self.flushes = 0

    def write(self, data: AnyStr) -> None:
        """
        Write data.

        @param data: data
        """
        self.writes += 1

    def flush(self) -> None:
        """
        Flush buffers.
        """
        self.flushes += 1

    def __enter__(self) -> "DummyFile":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        pass
