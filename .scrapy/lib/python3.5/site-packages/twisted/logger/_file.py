# -*- test-case-name: twisted.logger.test.test_file -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
File log observer.
"""

from zope.interface import implementer

from twisted.python.compat import ioType, unicode
from ._observer import ILogObserver
from ._format import formatTime
from ._format import timeFormatRFC3339
from ._format import formatEventAsClassicLogText



@implementer(ILogObserver)
class FileLogObserver(object):
    """
    Log observer that writes to a file-like object.
    """
    def __init__(self, outFile, formatEvent):
        """
        @param outFile: A file-like object.  Ideally one should be passed which
            accepts L{unicode} data.  Otherwise, UTF-8 L{bytes} will be used.
        @type outFile: L{io.IOBase}

        @param formatEvent: A callable that formats an event.
        @type formatEvent: L{callable} that takes an C{event} argument and
            returns a formatted event as L{unicode}.
        """
        if ioType(outFile) is not unicode:
            self._encoding = "utf-8"
        else:
            self._encoding = None

        self._outFile = outFile
        self.formatEvent = formatEvent


    def __call__(self, event):
        """
        Write event to file.

        @param event: An event.
        @type event: L{dict}
        """
        text = self.formatEvent(event)

        if text is None:
            text = u""

        if "log_failure" in event:
            try:
                traceback = event["log_failure"].getTraceback()
            except Exception:
                traceback = u"(UNABLE TO OBTAIN TRACEBACK FROM EVENT)\n"
            text = u"\n".join((text, traceback))

        if self._encoding is not None:
            text = text.encode(self._encoding)

        if text:
            self._outFile.write(text)
            self._outFile.flush()



def textFileLogObserver(outFile, timeFormat=timeFormatRFC3339):
    """
    Create a L{FileLogObserver} that emits text to a specified (writable)
    file-like object.

    @param outFile: A file-like object.  Ideally one should be passed which
        accepts L{unicode} data.  Otherwise, UTF-8 L{bytes} will be used.
    @type outFile: L{io.IOBase}

    @param timeFormat: The format to use when adding timestamp prefixes to
        logged events.  If L{None}, or for events with no C{"log_timestamp"}
        key, the default timestamp prefix of C{u"-"} is used.
    @type timeFormat: L{unicode} or L{None}

    @return: A file log observer.
    @rtype: L{FileLogObserver}
    """
    def formatEvent(event):
        return formatEventAsClassicLogText(
            event, formatTime=lambda e: formatTime(e, timeFormat)
        )

    return FileLogObserver(outFile, formatEvent)
