# -*- test-case-name: twisted.logger.test.test_file -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
File log observer.
"""

from typing import IO, Any, Callable, Optional

from zope.interface import implementer

from twisted.python.compat import ioType
from ._format import formatEventAsClassicLogText, formatTime, timeFormatRFC3339
from ._interfaces import ILogObserver, LogEvent


@implementer(ILogObserver)
class FileLogObserver:
    """
    Log observer that writes to a file-like object.
    """

    def __init__(
        self, outFile: IO[Any], formatEvent: Callable[[LogEvent], Optional[str]]
    ) -> None:
        """
        @param outFile: A file-like object.  Ideally one should be passed which
            accepts text data.  Otherwise, UTF-8 L{bytes} will be used.
        @param formatEvent: A callable that formats an event.
        """
        if ioType(outFile) is not str:
            self._encoding: Optional[str] = "utf-8"
        else:
            self._encoding = None

        self._outFile = outFile
        self.formatEvent = formatEvent

    def __call__(self, event: LogEvent) -> None:
        """
        Write event to file.

        @param event: An event.
        """
        text = self.formatEvent(event)

        if text:
            if self._encoding is None:
                self._outFile.write(text)
            else:
                self._outFile.write(text.encode(self._encoding))
            self._outFile.flush()


def textFileLogObserver(
    outFile: IO[Any], timeFormat: Optional[str] = timeFormatRFC3339
) -> FileLogObserver:
    """
    Create a L{FileLogObserver} that emits text to a specified (writable)
    file-like object.

    @param outFile: A file-like object.  Ideally one should be passed which
        accepts text data.  Otherwise, UTF-8 L{bytes} will be used.
    @param timeFormat: The format to use when adding timestamp prefixes to
        logged events.  If L{None}, or for events with no C{"log_timestamp"}
        key, the default timestamp prefix of C{"-"} is used.

    @return: A file log observer.
    """

    def formatEvent(event: LogEvent) -> Optional[str]:
        return formatEventAsClassicLogText(
            event, formatTime=lambda e: formatTime(e, timeFormat)
        )

    return FileLogObserver(outFile, formatEvent)
