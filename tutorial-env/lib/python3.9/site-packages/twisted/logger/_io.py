# -*- test-case-name: twisted.logger.test.test_io -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
File-like object that logs.
"""

import sys
from typing import AnyStr, Iterable, Optional

from constantly import NamedConstant  # type: ignore[import]
from incremental import Version

from twisted.python.deprecate import deprecatedProperty
from ._levels import LogLevel
from ._logger import Logger


class LoggingFile:
    """
    File-like object that turns C{write()} calls into logging events.

    Note that because event formats are L{str}, C{bytes} received via C{write()}
    are converted to C{str}, which is the opposite of what C{file} does.

    @ivar softspace: Attribute to make this class more file-like under Python 2;
        value is zero or one.  Do not use.
    """

    _softspace = 0

    @deprecatedProperty(Version("Twisted", 21, 2, 0))
    def softspace(self):
        return self._softspace

    @softspace.setter  # type: ignore[no-redef]
    def softspace(self, value):
        self._softspace = value

    def __init__(
        self,
        logger: Logger,
        level: NamedConstant = LogLevel.info,
        encoding: Optional[str] = None,
    ) -> None:
        """
        @param logger: the logger to log through.
        @param level: the log level to emit events with.
        @param encoding: The encoding to expect when receiving bytes via
            C{write()}.  If L{None}, use C{sys.getdefaultencoding()}.
        """
        self.level = level
        self.log = logger

        if encoding is None:
            self._encoding = sys.getdefaultencoding()
        else:
            self._encoding = encoding

        self._buffer = ""
        self._closed = False

    @property
    def closed(self) -> bool:
        """
        Read-only property.  Is the file closed?

        @return: true if closed, otherwise false.
        """
        return self._closed

    @property
    def encoding(self) -> str:
        """
        Read-only property.   File encoding.

        @return: an encoding.
        """
        return self._encoding

    @property
    def mode(self) -> str:
        """
        Read-only property.  File mode.

        @return: "w"
        """
        return "w"

    @property
    def newlines(self) -> None:
        """
        Read-only property.  Types of newlines encountered.

        @return: L{None}
        """
        return None

    @property
    def name(self) -> str:
        """
        The name of this file; a repr-style string giving information about its
        namespace.

        @return: A file name.
        """
        return "<{} {}#{}>".format(
            self.__class__.__name__,
            self.log.namespace,
            self.level.name,
        )

    def close(self) -> None:
        """
        Close this file so it can no longer be written to.
        """
        self._closed = True

    def flush(self) -> None:
        """
        No-op; this file does not buffer.
        """
        pass

    def fileno(self) -> int:
        """
        Returns an invalid file descriptor, since this is not backed by an FD.

        @return: C{-1}
        """
        return -1

    def isatty(self) -> bool:
        """
        A L{LoggingFile} is not a TTY.

        @return: C{False}
        """
        return False

    def write(self, message: AnyStr) -> None:
        """
        Log the given message.

        @param message: The message to write.
        """
        if self._closed:
            raise ValueError("I/O operation on closed file")

        if isinstance(message, bytes):
            text = message.decode(self._encoding)
        else:
            text = message

        lines = (self._buffer + text).split("\n")
        self._buffer = lines[-1]
        lines = lines[0:-1]

        for line in lines:
            self.log.emit(self.level, format="{log_io}", log_io=line)

    def writelines(self, lines: Iterable[AnyStr]) -> None:
        """
        Log each of the given lines as a separate message.

        @param lines: Data to write.
        """
        for line in lines:
            self.write(line)

    def _unsupported(self, *args: object) -> None:
        """
        Template for unsupported operations.

        @param args: Arguments.
        """
        raise OSError("unsupported operation")

    read = _unsupported
    next = _unsupported
    readline = _unsupported
    readlines = _unsupported
    xreadlines = _unsupported
    seek = _unsupported
    tell = _unsupported
    truncate = _unsupported
