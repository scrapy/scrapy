# -*- test-case-name: twisted.logger.test.test_io -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
File-like object that logs.
"""

import sys

from ._levels import LogLevel



class LoggingFile(object):
    """
    File-like object that turns C{write()} calls into logging events.

    Note that because event formats are C{unicode}, C{bytes} received via
    C{write()} are converted to C{unicode}, which is the opposite of what
    C{file} does.

    @ivar softspace: File-like L{'softspace' attribute <file.softspace>}; zero
        or one.
    @type softspace: L{int}
    """

    softspace = 0


    def __init__(self, logger, level=LogLevel.info, encoding=None):
        """
        @param logger: the logger to log through.

        @param level: the log level to emit events with.

        @param encoding: The encoding to expect when receiving bytes via
            C{write()}.  If L{None}, use C{sys.getdefaultencoding()}.
        @type encoding: L{str}

        @param log: The logger to send events to.
        @type log: L{Logger}
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
    def closed(self):
        """
        Read-only property.  Is the file closed?

        @return: true if closed, otherwise false.
        @rtype: L{bool}
        """
        return self._closed


    @property
    def encoding(self):
        """
        Read-only property.   File encoding.

        @return: an encoding.
        @rtype: L{str}
        """
        return self._encoding


    @property
    def mode(self):
        """
        Read-only property.  File mode.

        @return: "w"
        @rtype: L{str}
        """
        return "w"


    @property
    def newlines(self):
        """
        Read-only property.  Types of newlines encountered.

        @return: L{None}
        @rtype: L{None}
        """
        return None


    @property
    def name(self):
        """
        The name of this file; a repr-style string giving information about its
        namespace.

        @return: A file name.
        @rtype: L{str}
        """
        return (
            "<{0} {1}#{2}>".format(
                self.__class__.__name__,
                self.log.namespace,
                self.level.name,
            )
        )


    def close(self):
        """
        Close this file so it can no longer be written to.
        """
        self._closed = True


    def flush(self):
        """
        No-op; this file does not buffer.
        """
        pass


    def fileno(self):
        """
        Returns an invalid file descriptor, since this is not backed by an FD.

        @return: C{-1}
        @rtype: L{int}
        """
        return -1


    def isatty(self):
        """
        A L{LoggingFile} is not a TTY.

        @return: C{False}
        @rtype: L{bool}
        """
        return False


    def write(self, string):
        """
        Log the given message.

        @param string: Data to write.
        @type string: L{bytes} in this file's preferred encoding or L{unicode}
        """
        if self._closed:
            raise ValueError("I/O operation on closed file")

        if isinstance(string, bytes):
            string = string.decode(self._encoding)

        lines = (self._buffer + string).split("\n")
        self._buffer = lines[-1]
        lines = lines[0:-1]

        for line in lines:
            self.log.emit(self.level, format=u"{log_io}", log_io=line)


    def writelines(self, lines):
        """
        Log each of the given lines as a separate message.

        @param lines: Data to write.
        @type lines: iterable of L{unicode} or L{bytes} in this file's
            declared encoding
        """
        for line in lines:
            self.write(line)


    def _unsupported(self, *args):
        """
        Template for unsupported operations.

        @param args: Arguments.
        @type args: tuple of L{object}
        """
        raise IOError("unsupported operation")


    read       = _unsupported
    next       = _unsupported
    readline   = _unsupported
    readlines  = _unsupported
    xreadlines = _unsupported
    seek       = _unsupported
    tell       = _unsupported
    truncate   = _unsupported
