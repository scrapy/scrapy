# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.fdesc}.
"""

import errno
import os
import sys

try:
    import fcntl
except ImportError:
    skip = "not supported on this platform"
else:
    from twisted.internet import fdesc

from twisted.python.util import untilConcludes
from twisted.trial import unittest


class NonBlockingTests(unittest.SynchronousTestCase):
    """
    Tests for L{fdesc.setNonBlocking} and L{fdesc.setBlocking}.
    """

    def test_setNonBlocking(self):
        """
        L{fdesc.setNonBlocking} sets a file description to non-blocking.
        """
        r, w = os.pipe()
        self.addCleanup(os.close, r)
        self.addCleanup(os.close, w)
        self.assertFalse(fcntl.fcntl(r, fcntl.F_GETFL) & os.O_NONBLOCK)
        fdesc.setNonBlocking(r)
        self.assertTrue(fcntl.fcntl(r, fcntl.F_GETFL) & os.O_NONBLOCK)

    def test_setBlocking(self):
        """
        L{fdesc.setBlocking} sets a file description to blocking.
        """
        r, w = os.pipe()
        self.addCleanup(os.close, r)
        self.addCleanup(os.close, w)
        fdesc.setNonBlocking(r)
        fdesc.setBlocking(r)
        self.assertFalse(fcntl.fcntl(r, fcntl.F_GETFL) & os.O_NONBLOCK)


class ReadWriteTests(unittest.SynchronousTestCase):
    """
    Tests for L{fdesc.readFromFD}, L{fdesc.writeToFD}.
    """

    def setUp(self):
        """
        Create a non-blocking pipe that can be used in tests.
        """
        self.r, self.w = os.pipe()
        fdesc.setNonBlocking(self.r)
        fdesc.setNonBlocking(self.w)

    def tearDown(self):
        """
        Close pipes.
        """
        try:
            os.close(self.w)
        except OSError:
            pass
        try:
            os.close(self.r)
        except OSError:
            pass

    def write(self, d):
        """
        Write data to the pipe.
        """
        return fdesc.writeToFD(self.w, d)

    def read(self):
        """
        Read data from the pipe.
        """
        l = []
        res = fdesc.readFromFD(self.r, l.append)
        if res is None:
            if l:
                return l[0]
            else:
                return b""
        else:
            return res

    def test_writeAndRead(self):
        """
        Test that the number of bytes L{fdesc.writeToFD} reports as written
        with its return value are seen by L{fdesc.readFromFD}.
        """
        n = self.write(b"hello")
        self.assertTrue(n > 0)
        s = self.read()
        self.assertEqual(len(s), n)
        self.assertEqual(b"hello"[:n], s)

    def test_writeAndReadLarge(self):
        """
        Similar to L{test_writeAndRead}, but use a much larger string to verify
        the behavior for that case.
        """
        orig = b"0123456879" * 10000
        written = self.write(orig)
        self.assertTrue(written > 0)
        result = []
        resultlength = 0
        i = 0
        while resultlength < written or i < 50:
            result.append(self.read())
            resultlength += len(result[-1])
            # Increment a counter to be sure we'll exit at some point
            i += 1
        result = b"".join(result)
        self.assertEqual(len(result), written)
        self.assertEqual(orig[:written], result)

    def test_readFromEmpty(self):
        """
        Verify that reading from a file descriptor with no data does not raise
        an exception and does not result in the callback function being called.
        """
        l = []
        result = fdesc.readFromFD(self.r, l.append)
        self.assertEqual(l, [])
        self.assertIsNone(result)

    def test_readFromCleanClose(self):
        """
        Test that using L{fdesc.readFromFD} on a cleanly closed file descriptor
        returns a connection done indicator.
        """
        os.close(self.w)
        self.assertEqual(self.read(), fdesc.CONNECTION_DONE)

    def test_writeToClosed(self):
        """
        Verify that writing with L{fdesc.writeToFD} when the read end is closed
        results in a connection lost indicator.
        """
        os.close(self.r)
        self.assertEqual(self.write(b"s"), fdesc.CONNECTION_LOST)

    def test_readFromInvalid(self):
        """
        Verify that reading with L{fdesc.readFromFD} when the read end is
        closed results in a connection lost indicator.
        """
        os.close(self.r)
        self.assertEqual(self.read(), fdesc.CONNECTION_LOST)

    def test_writeToInvalid(self):
        """
        Verify that writing with L{fdesc.writeToFD} when the write end is
        closed results in a connection lost indicator.
        """
        os.close(self.w)
        self.assertEqual(self.write(b"s"), fdesc.CONNECTION_LOST)

    def test_writeErrors(self):
        """
        Test error path for L{fdesc.writeTod}.
        """
        oldOsWrite = os.write

        def eagainWrite(fd, data):
            err = OSError()
            err.errno = errno.EAGAIN
            raise err

        os.write = eagainWrite
        try:
            self.assertEqual(self.write(b"s"), 0)
        finally:
            os.write = oldOsWrite

        def eintrWrite(fd, data):
            err = OSError()
            err.errno = errno.EINTR
            raise err

        os.write = eintrWrite
        try:
            self.assertEqual(self.write(b"s"), 0)
        finally:
            os.write = oldOsWrite


class CloseOnExecTests(unittest.SynchronousTestCase):
    """
    Tests for L{fdesc._setCloseOnExec} and L{fdesc._unsetCloseOnExec}.
    """

    program = """
import os, errno
try:
    os.write(%d, b'lul')
except OSError as e:
    if e.errno == errno.EBADF:
        os._exit(0)
    os._exit(5)
except BaseException:
    os._exit(10)
else:
    os._exit(20)
"""

    def _execWithFileDescriptor(self, fObj):
        pid = os.fork()
        if pid == 0:
            try:
                os.execv(
                    sys.executable,
                    [sys.executable, "-c", self.program % (fObj.fileno(),)],
                )
            except BaseException:
                import traceback

                traceback.print_exc()
                os._exit(30)
        else:
            # On Linux wait(2) doesn't seem ever able to fail with EINTR but
            # POSIX seems to allow it and on macOS it happens quite a lot.
            return untilConcludes(os.waitpid, pid, 0)[1]

    def test_setCloseOnExec(self):
        """
        A file descriptor passed to L{fdesc._setCloseOnExec} is not inherited
        by a new process image created with one of the exec family of
        functions.
        """
        with open(self.mktemp(), "wb") as fObj:
            fdesc._setCloseOnExec(fObj.fileno())
            status = self._execWithFileDescriptor(fObj)
            self.assertTrue(os.WIFEXITED(status))
            self.assertEqual(os.WEXITSTATUS(status), 0)

    def test_unsetCloseOnExec(self):
        """
        A file descriptor passed to L{fdesc._unsetCloseOnExec} is inherited by
        a new process image created with one of the exec family of functions.
        """
        with open(self.mktemp(), "wb") as fObj:
            fdesc._setCloseOnExec(fObj.fileno())
            fdesc._unsetCloseOnExec(fObj.fileno())
            status = self._execWithFileDescriptor(fObj)
            self.assertTrue(os.WIFEXITED(status))
            self.assertEqual(os.WEXITSTATUS(status), 20)
