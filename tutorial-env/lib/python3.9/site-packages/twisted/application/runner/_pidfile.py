# -*- test-case-name: twisted.application.runner.test.test_pidfile -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
PID file.
"""

import errno
from os import getpid, kill, name as SYSTEM_NAME
from types import TracebackType
from typing import Optional, Type

from zope.interface import Interface, implementer

from twisted.logger import Logger
from twisted.python.filepath import FilePath


class IPIDFile(Interface):
    """
    Manages a file that remembers a process ID.
    """

    def read() -> int:
        """
        Read the process ID stored in this PID file.

        @return: The contained process ID.

        @raise NoPIDFound: If this PID file does not exist.
        @raise EnvironmentError: If this PID file cannot be read.
        @raise ValueError: If this PID file's content is invalid.
        """

    def writeRunningPID() -> None:
        """
        Store the PID of the current process in this PID file.

        @raise EnvironmentError: If this PID file cannot be written.
        """

    def remove() -> None:
        """
        Remove this PID file.

        @raise EnvironmentError: If this PID file cannot be removed.
        """

    def isRunning() -> bool:
        """
        Determine whether there is a running process corresponding to the PID
        in this PID file.

        @return: True if this PID file contains a PID and a process with that
            PID is currently running; false otherwise.

        @raise EnvironmentError: If this PID file cannot be read.
        @raise InvalidPIDFileError: If this PID file's content is invalid.
        @raise StalePIDFileError: If this PID file's content refers to a PID
            for which there is no corresponding running process.
        """

    def __enter__() -> "IPIDFile":
        """
        Enter a context using this PIDFile.

        Writes the PID file with the PID of the running process.

        @raise AlreadyRunningError: A process corresponding to the PID in this
            PID file is already running.
        """

    def __exit__(
        excType: Optional[Type[BaseException]],
        excValue: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        """
        Exit a context using this PIDFile.

        Removes the PID file.
        """


@implementer(IPIDFile)
class PIDFile:
    """
    Concrete implementation of L{IPIDFile}.

    This implementation is presently not supported on non-POSIX platforms.
    Specifically, calling L{PIDFile.isRunning} will raise
    L{NotImplementedError}.
    """

    _log = Logger()

    @staticmethod
    def _format(pid: int) -> bytes:
        """
        Format a PID file's content.

        @param pid: A process ID.

        @return: Formatted PID file contents.
        """
        return f"{int(pid)}\n".encode()

    def __init__(self, filePath: FilePath) -> None:
        """
        @param filePath: The path to the PID file on disk.
        """
        self.filePath = filePath

    def read(self) -> int:
        pidString = b""
        try:
            with self.filePath.open() as fh:
                for pidString in fh:
                    break
        except OSError as e:
            if e.errno == errno.ENOENT:  # No such file
                raise NoPIDFound("PID file does not exist")
            raise

        try:
            return int(pidString)
        except ValueError:
            raise InvalidPIDFileError(
                f"non-integer PID value in PID file: {pidString!r}"
            )

    def _write(self, pid: int) -> None:
        """
        Store a PID in this PID file.

        @param pid: A PID to store.

        @raise EnvironmentError: If this PID file cannot be written.
        """
        self.filePath.setContent(self._format(pid=pid))

    def writeRunningPID(self) -> None:
        self._write(getpid())

    def remove(self) -> None:
        self.filePath.remove()

    def isRunning(self) -> bool:
        try:
            pid = self.read()
        except NoPIDFound:
            return False

        if SYSTEM_NAME == "posix":
            return self._pidIsRunningPOSIX(pid)
        else:
            raise NotImplementedError(f"isRunning is not implemented on {SYSTEM_NAME}")

    @staticmethod
    def _pidIsRunningPOSIX(pid: int) -> bool:
        """
        POSIX implementation for running process check.

        Determine whether there is a running process corresponding to the given
        PID.

        @param pid: The PID to check.

        @return: True if the given PID is currently running; false otherwise.

        @raise EnvironmentError: If this PID file cannot be read.
        @raise InvalidPIDFileError: If this PID file's content is invalid.
        @raise StalePIDFileError: If this PID file's content refers to a PID
            for which there is no corresponding running process.
        """
        try:
            kill(pid, 0)
        except OSError as e:
            if e.errno == errno.ESRCH:  # No such process
                raise StalePIDFileError("PID file refers to non-existing process")
            elif e.errno == errno.EPERM:  # Not permitted to kill
                return True
            else:
                raise
        else:
            return True

    def __enter__(self) -> "PIDFile":
        try:
            if self.isRunning():
                raise AlreadyRunningError()
        except StalePIDFileError:
            self._log.info("Replacing stale PID file: {log_source}")
        self.writeRunningPID()
        return self

    def __exit__(
        self,
        excType: Optional[Type[BaseException]],
        excValue: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.remove()
        return None


@implementer(IPIDFile)
class NonePIDFile:
    """
    PID file implementation that does nothing.

    This is meant to be used as a "active None" object in place of a PID file
    when no PID file is desired.
    """

    def __init__(self) -> None:
        pass

    def read(self) -> int:
        raise NoPIDFound("PID file does not exist")

    def _write(self, pid: int) -> None:
        """
        Store a PID in this PID file.

        @param pid: A PID to store.

        @raise EnvironmentError: If this PID file cannot be written.

        @note: This implementation always raises an L{EnvironmentError}.
        """
        raise OSError(errno.EPERM, "Operation not permitted")

    def writeRunningPID(self) -> None:
        self._write(0)

    def remove(self) -> None:
        raise OSError(errno.ENOENT, "No such file or directory")

    def isRunning(self) -> bool:
        return False

    def __enter__(self) -> "NonePIDFile":
        return self

    def __exit__(
        self,
        excType: Optional[Type[BaseException]],
        excValue: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        return None


nonePIDFile: IPIDFile = NonePIDFile()


class AlreadyRunningError(Exception):
    """
    Process is already running.
    """


class InvalidPIDFileError(Exception):
    """
    PID file contents are invalid.
    """


class StalePIDFileError(Exception):
    """
    PID file contents are valid, but there is no process with the referenced
    PID.
    """


class NoPIDFound(Exception):
    """
    No PID found in PID file.
    """
