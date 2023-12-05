# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.application.runner._pidfile}.
"""

import errno
from functools import wraps
from os import getpid, name as SYSTEM_NAME
from typing import Any, Callable, Optional

from zope.interface.verify import verifyObject

import twisted.trial.unittest
from twisted.python.filepath import FilePath
from twisted.python.runtime import platform
from twisted.trial.unittest import SkipTest
from ...runner import _pidfile
from .._pidfile import (
    AlreadyRunningError,
    InvalidPIDFileError,
    IPIDFile,
    NonePIDFile,
    NoPIDFound,
    PIDFile,
    StalePIDFileError,
)


def ifPlatformSupported(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator for tests that are not expected to work on all platforms.

    Calling L{PIDFile.isRunning} currently raises L{NotImplementedError} on
    non-POSIX platforms.

    On an unsupported platform, we expect to see any test that calls
    L{PIDFile.isRunning} to raise either L{NotImplementedError}, L{SkipTest},
    or C{self.failureException}.
    (C{self.failureException} may occur in a test that checks for a specific
    exception but it gets NotImplementedError instead.)

    @param f: The test method to decorate.

    @return: The wrapped callable.
    """

    @wraps(f)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        supported = platform.getType() == "posix"

        if supported:
            return f(self, *args, **kwargs)
        else:
            e = self.assertRaises(
                (NotImplementedError, SkipTest, self.failureException),
                f,
                self,
                *args,
                **kwargs,
            )
            if isinstance(e, NotImplementedError):
                self.assertTrue(str(e).startswith("isRunning is not implemented on "))

    return wrapper


class PIDFileTests(twisted.trial.unittest.TestCase):
    """
    Tests for L{PIDFile}.
    """

    def filePath(self, content: Optional[bytes] = None) -> FilePath:
        filePath = FilePath(self.mktemp())
        if content is not None:
            filePath.setContent(content)
        return filePath

    def test_interface(self) -> None:
        """
        L{PIDFile} conforms to L{IPIDFile}.
        """
        pidFile = PIDFile(self.filePath())
        verifyObject(IPIDFile, pidFile)

    def test_formatWithPID(self) -> None:
        """
        L{PIDFile._format} returns the expected format when given a PID.
        """
        self.assertEqual(PIDFile._format(pid=1337), b"1337\n")

    def test_readWithPID(self) -> None:
        """
        L{PIDFile.read} returns the PID from the given file path.
        """
        pid = 1337

        pidFile = PIDFile(self.filePath(PIDFile._format(pid=pid)))

        self.assertEqual(pid, pidFile.read())

    def test_readEmptyPID(self) -> None:
        """
        L{PIDFile.read} raises L{InvalidPIDFileError} when given an empty file
        path.
        """
        pidValue = b""
        pidFile = PIDFile(self.filePath(b""))

        e = self.assertRaises(InvalidPIDFileError, pidFile.read)
        self.assertEqual(str(e), f"non-integer PID value in PID file: {pidValue!r}")

    def test_readWithBogusPID(self) -> None:
        """
        L{PIDFile.read} raises L{InvalidPIDFileError} when given an empty file
        path.
        """
        pidValue = b"$foo!"
        pidFile = PIDFile(self.filePath(pidValue))

        e = self.assertRaises(InvalidPIDFileError, pidFile.read)
        self.assertEqual(str(e), f"non-integer PID value in PID file: {pidValue!r}")

    def test_readDoesntExist(self) -> None:
        """
        L{PIDFile.read} raises L{NoPIDFound} when given a non-existing file
        path.
        """
        pidFile = PIDFile(self.filePath())

        e = self.assertRaises(NoPIDFound, pidFile.read)
        self.assertEqual(str(e), "PID file does not exist")

    def test_readOpenRaisesOSErrorNotENOENT(self) -> None:
        """
        L{PIDFile.read} re-raises L{OSError} if the associated C{errno} is
        anything other than L{errno.ENOENT}.
        """

        def oops(mode: str = "r") -> FilePath:
            raise OSError(errno.EIO, "I/O error")

        self.patch(FilePath, "open", oops)

        pidFile = PIDFile(self.filePath())

        error = self.assertRaises(OSError, pidFile.read)
        self.assertEqual(error.errno, errno.EIO)

    def test_writePID(self) -> None:
        """
        L{PIDFile._write} stores the given PID.
        """
        pid = 1995

        pidFile = PIDFile(self.filePath())
        pidFile._write(pid)

        self.assertEqual(pidFile.read(), pid)

    def test_writePIDInvalid(self) -> None:
        """
        L{PIDFile._write} raises L{ValueError} when given an invalid PID.
        """
        pidFile = PIDFile(self.filePath())

        self.assertRaises(ValueError, pidFile._write, "burp")

    def test_writeRunningPID(self) -> None:
        """
        L{PIDFile.writeRunningPID} stores the PID for the current process.
        """
        pidFile = PIDFile(self.filePath())
        pidFile.writeRunningPID()

        self.assertEqual(pidFile.read(), getpid())

    def test_remove(self) -> None:
        """
        L{PIDFile.remove} removes the PID file.
        """
        pidFile = PIDFile(self.filePath(b""))
        self.assertTrue(pidFile.filePath.exists())

        pidFile.remove()
        self.assertFalse(pidFile.filePath.exists())

    @ifPlatformSupported
    def test_isRunningDoesExist(self) -> None:
        """
        L{PIDFile.isRunning} returns true for a process that does exist.
        """
        pidFile = PIDFile(self.filePath())
        pidFile._write(1337)

        def kill(pid: int, signal: int) -> None:
            return  # Don't actually kill anything

        self.patch(_pidfile, "kill", kill)

        self.assertTrue(pidFile.isRunning())

    @ifPlatformSupported
    def test_isRunningThis(self) -> None:
        """
        L{PIDFile.isRunning} returns true for this process (which is running).

        @note: This differs from L{PIDFileTests.test_isRunningDoesExist} in
        that it actually invokes the C{kill} system call, which is useful for
        testing of our chosen method for probing the existence of a process.
        """
        pidFile = PIDFile(self.filePath())
        pidFile.writeRunningPID()

        self.assertTrue(pidFile.isRunning())

    @ifPlatformSupported
    def test_isRunningDoesNotExist(self) -> None:
        """
        L{PIDFile.isRunning} raises L{StalePIDFileError} for a process that
        does not exist (errno=ESRCH).
        """
        pidFile = PIDFile(self.filePath())
        pidFile._write(1337)

        def kill(pid: int, signal: int) -> None:
            raise OSError(errno.ESRCH, "No such process")

        self.patch(_pidfile, "kill", kill)

        self.assertRaises(StalePIDFileError, pidFile.isRunning)

    @ifPlatformSupported
    def test_isRunningNotAllowed(self) -> None:
        """
        L{PIDFile.isRunning} returns true for a process that we are not allowed
        to kill (errno=EPERM).
        """
        pidFile = PIDFile(self.filePath())
        pidFile._write(1337)

        def kill(pid: int, signal: int) -> None:
            raise OSError(errno.EPERM, "Operation not permitted")

        self.patch(_pidfile, "kill", kill)

        self.assertTrue(pidFile.isRunning())

    @ifPlatformSupported
    def test_isRunningInit(self) -> None:
        """
        L{PIDFile.isRunning} returns true for a process that we are not allowed
        to kill (errno=EPERM).

        @note: This differs from L{PIDFileTests.test_isRunningNotAllowed} in
        that it actually invokes the C{kill} system call, which is useful for
        testing of our chosen method for probing the existence of a process
        that we are not allowed to kill.

        @note: In this case, we try killing C{init}, which is process #1 on
        POSIX systems, so this test is not portable.  C{init} should always be
        running and should not be killable by non-root users.
        """
        if SYSTEM_NAME != "posix":
            raise SkipTest("This test assumes POSIX")

        pidFile = PIDFile(self.filePath())
        pidFile._write(1)  # PID 1 is init on POSIX systems

        self.assertTrue(pidFile.isRunning())

    @ifPlatformSupported
    def test_isRunningUnknownErrno(self) -> None:
        """
        L{PIDFile.isRunning} re-raises L{OSError} if the attached C{errno}
        value from L{os.kill} is not an expected one.
        """
        pidFile = PIDFile(self.filePath())
        pidFile.writeRunningPID()

        def kill(pid: int, signal: int) -> None:
            raise OSError(errno.EEXIST, "File exists")

        self.patch(_pidfile, "kill", kill)

        self.assertRaises(OSError, pidFile.isRunning)

    def test_isRunningNoPIDFile(self) -> None:
        """
        L{PIDFile.isRunning} returns false if the PID file doesn't exist.
        """
        pidFile = PIDFile(self.filePath())

        self.assertFalse(pidFile.isRunning())

    def test_contextManager(self) -> None:
        """
        When used as a context manager, a L{PIDFile} will store the current pid
        on entry, then removes the PID file on exit.
        """
        pidFile = PIDFile(self.filePath())
        self.assertFalse(pidFile.filePath.exists())

        with pidFile:
            self.assertTrue(pidFile.filePath.exists())
            self.assertEqual(pidFile.read(), getpid())

        self.assertFalse(pidFile.filePath.exists())

    @ifPlatformSupported
    def test_contextManagerDoesntExist(self) -> None:
        """
        When used as a context manager, a L{PIDFile} will replace the
        underlying PIDFile rather than raising L{AlreadyRunningError} if the
        contained PID file exists but refers to a non-running PID.
        """
        pidFile = PIDFile(self.filePath())
        pidFile._write(1337)

        def kill(pid: int, signal: int) -> None:
            raise OSError(errno.ESRCH, "No such process")

        self.patch(_pidfile, "kill", kill)

        e = self.assertRaises(StalePIDFileError, pidFile.isRunning)
        self.assertEqual(str(e), "PID file refers to non-existing process")

        with pidFile:
            self.assertEqual(pidFile.read(), getpid())

    @ifPlatformSupported
    def test_contextManagerAlreadyRunning(self) -> None:
        """
        When used as a context manager, a L{PIDFile} will raise
        L{AlreadyRunningError} if the there is already a running process with
        the contained PID.
        """
        pidFile = PIDFile(self.filePath())
        pidFile._write(1337)

        def kill(pid: int, signal: int) -> None:
            return  # Don't actually kill anything

        self.patch(_pidfile, "kill", kill)

        self.assertTrue(pidFile.isRunning())

        self.assertRaises(AlreadyRunningError, pidFile.__enter__)


class NonePIDFileTests(twisted.trial.unittest.TestCase):
    """
    Tests for L{NonePIDFile}.
    """

    def test_interface(self) -> None:
        """
        L{NonePIDFile} conforms to L{IPIDFile}.
        """
        pidFile = NonePIDFile()
        verifyObject(IPIDFile, pidFile)

    def test_read(self) -> None:
        """
        L{NonePIDFile.read} raises L{NoPIDFound}.
        """
        pidFile = NonePIDFile()

        e = self.assertRaises(NoPIDFound, pidFile.read)
        self.assertEqual(str(e), "PID file does not exist")

    def test_write(self) -> None:
        """
        L{NonePIDFile._write} raises L{OSError} with an errno of L{errno.EPERM}.
        """
        pidFile = NonePIDFile()

        error = self.assertRaises(OSError, pidFile._write, 0)
        self.assertEqual(error.errno, errno.EPERM)

    def test_writeRunningPID(self) -> None:
        """
        L{NonePIDFile.writeRunningPID} raises L{OSError} with an errno of
        L{errno.EPERM}.
        """
        pidFile = NonePIDFile()

        error = self.assertRaises(OSError, pidFile.writeRunningPID)
        self.assertEqual(error.errno, errno.EPERM)

    def test_remove(self) -> None:
        """
        L{NonePIDFile.remove} raises L{OSError} with an errno of L{errno.EPERM}.
        """
        pidFile = NonePIDFile()

        error = self.assertRaises(OSError, pidFile.remove)
        self.assertEqual(error.errno, errno.ENOENT)

    def test_isRunning(self) -> None:
        """
        L{NonePIDFile.isRunning} returns L{False}.
        """
        pidFile = NonePIDFile()

        self.assertEqual(pidFile.isRunning(), False)

    def test_contextManager(self) -> None:
        """
        When used as a context manager, a L{NonePIDFile} doesn't raise, despite
        not existing.
        """
        pidFile = NonePIDFile()

        with pidFile:
            pass
